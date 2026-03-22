"""Tests for pfb.framebuffer."""

import unittest
import unittest.mock

import numpy
import PIL.Image

import pfb.framebuffer


def _make_fb(width: int = 800, height: int = 600, bpp: int = 32) -> tuple:
    """Return a Framebuffer backed by a mock libpyfb instance."""
    mock_libpyfb_fb = unittest.mock.MagicMock()
    mock_libpyfb_fb.screenx = width
    mock_libpyfb_fb.screeny = height
    mock_libpyfb_fb.bpp = bpp
    mock_libpyfb_fb.fb = unittest.mock.MagicMock()

    with unittest.mock.patch("pfb.libpyfb.Framebuffer", return_value=mock_libpyfb_fb):
        fb = pfb.framebuffer.Framebuffer("/dev/fb0")

    return fb, mock_libpyfb_fb


class TestFitImage(unittest.TestCase):
    def setUp(self):
        self.fb, _ = _make_fb(800, 600)

    def test_output_is_screen_size(self):
        # Any input image must produce a canvas of exactly screen dimensions.
        img = PIL.Image.new("RGB", (1920, 1080))
        result = self.fb._fit_image(img)
        self.assertEqual(result.size, (800, 600))

    def test_wide_image_letterboxed(self):
        # A wider-than-screen image must be pillar/letterboxed with black rows.
        img = PIL.Image.new("RGB", (1600, 200), (255, 255, 255))
        result = self.fb._fit_image(img)
        arr = numpy.array(result)
        # Top row should be black padding.
        self.assertTrue(numpy.all(arr[0] == 0))

    def test_tall_image_pillarboxed(self):
        # A taller-than-screen image must be pillarboxed with black columns.
        img = PIL.Image.new("RGB", (100, 1200), (255, 255, 255))
        result = self.fb._fit_image(img)
        arr = numpy.array(result)
        # Left column should be black padding.
        self.assertTrue(numpy.all(arr[:, 0] == 0))

    def test_rgba_converted_to_rgb(self):
        # RGBA input must be converted to RGB before encoding.
        img = PIL.Image.new("RGBA", (800, 600), (255, 0, 0, 128))
        result = self.fb._fit_image(img)
        self.assertEqual(result.mode, "RGB")

    def test_exact_size_image_no_padding(self):
        # An image that exactly matches screen dimensions needs no padding.
        img = PIL.Image.new("RGB", (800, 600), (128, 64, 32))
        result = self.fb._fit_image(img)
        arr = numpy.array(result)
        self.assertTrue(numpy.all(arr == numpy.array([128, 64, 32])))


class TestEncode32bpp(unittest.TestCase):
    def setUp(self):
        # 1×1 screen simplifies byte-level assertions.
        self.fb, _ = _make_fb(1, 1, 32)

    def test_pure_red_maps_to_bgrt(self):
        # Red (255,0,0) → B=0, G=0, R=255, T=0
        img = PIL.Image.new("RGB", (1, 1), (255, 0, 0))
        self.assertEqual(self.fb._encode(img), bytes([0, 0, 255, 0]))

    def test_pure_green_maps_to_bgrt(self):
        # Green (0,255,0) → B=0, G=255, R=0, T=0
        img = PIL.Image.new("RGB", (1, 1), (0, 255, 0))
        self.assertEqual(self.fb._encode(img), bytes([0, 255, 0, 0]))

    def test_pure_blue_maps_to_bgrt(self):
        # Blue (0,0,255) → B=255, G=0, R=0, T=0
        img = PIL.Image.new("RGB", (1, 1), (0, 0, 255))
        self.assertEqual(self.fb._encode(img), bytes([255, 0, 0, 0]))

    def test_output_length(self):
        # 4×3 image at 32 bpp → 4 * 3 * 4 bytes
        fb, _ = _make_fb(4, 3, 32)
        img = PIL.Image.new("RGB", (4, 3))
        self.assertEqual(len(fb._encode(img)), 48)


class TestEncode16bpp(unittest.TestCase):
    def setUp(self):
        self.fb, _ = _make_fb(1, 1, 16)

    def _decode(self, data: bytes) -> int:
        # Reconstruct the uint16 value from raw bytes using numpy's native endianness.
        return int(numpy.frombuffer(data, dtype=numpy.uint16)[0])

    def test_pure_red_rgb565(self):
        # Red: r=31 (255>>3), g=0, b=0 → 0xF800
        img = PIL.Image.new("RGB", (1, 1), (255, 0, 0))
        self.assertEqual(self._decode(self.fb._encode(img)), 0xF800)

    def test_pure_green_rgb565(self):
        # Green: r=0, g=63 (255>>2), b=0 → 0x07E0
        img = PIL.Image.new("RGB", (1, 1), (0, 255, 0))
        self.assertEqual(self._decode(self.fb._encode(img)), 0x07E0)

    def test_pure_blue_rgb565(self):
        # Blue: r=0, g=0, b=31 (255>>3) → 0x001F
        img = PIL.Image.new("RGB", (1, 1), (0, 0, 255))
        self.assertEqual(self._decode(self.fb._encode(img)), 0x001F)

    def test_output_length(self):
        # 4×3 image at 16 bpp → 4 * 3 * 2 bytes
        fb, _ = _make_fb(4, 3, 16)
        img = PIL.Image.new("RGB", (4, 3))
        self.assertEqual(len(fb._encode(img)), 24)


class TestExtractExifText(unittest.TestCase):
    def _make_img(self, exif_dict: dict) -> PIL.Image.Image:
        # Return a mock image whose getexif() returns the given dict.
        img = unittest.mock.MagicMock(spec=PIL.Image.Image)
        img.getexif.return_value = exif_dict
        return img

    def test_both_timestamp_and_model(self):
        # When both fields are present, timestamp appears to the left of model.
        img = self._make_img({36867: "2024:01:15 10:30:00", 272: "Canon EOS R5"})
        self.assertEqual(
            pfb.framebuffer._extract_exif_text(img, show_timestamp=True, show_model=True),
            "2024:01:15 10:30:00  Canon EOS R5",
        )

    def test_timestamp_only(self):
        img = self._make_img({36867: "2024:01:15 10:30:00"})
        self.assertEqual(
            pfb.framebuffer._extract_exif_text(img, show_timestamp=True, show_model=False),
            "2024:01:15 10:30:00",
        )

    def test_model_only(self):
        img = self._make_img({272: "Nikon Z9"})
        self.assertEqual(
            pfb.framebuffer._extract_exif_text(img, show_timestamp=False, show_model=True),
            "Nikon Z9",
        )

    def test_show_timestamp_false_suppresses_timestamp(self):
        # Even when EXIF has a timestamp, it must not appear if show_timestamp=False.
        img = self._make_img({36867: "2024:01:15 10:30:00", 272: "Canon EOS R5"})
        result = pfb.framebuffer._extract_exif_text(img, show_timestamp=False, show_model=True)
        self.assertEqual(result, "Canon EOS R5")

    def test_show_model_false_suppresses_model(self):
        # Even when EXIF has a model, it must not appear if show_model=False.
        img = self._make_img({36867: "2024:01:15 10:30:00", 272: "Canon EOS R5"})
        result = pfb.framebuffer._extract_exif_text(img, show_timestamp=True, show_model=False)
        self.assertEqual(result, "2024:01:15 10:30:00")

    def test_both_false_returns_none_without_reading_exif(self):
        # When neither field is requested, getexif must not be called at all.
        img = unittest.mock.MagicMock(spec=PIL.Image.Image)
        result = pfb.framebuffer._extract_exif_text(img, show_timestamp=False, show_model=False)
        self.assertIsNone(result)
        img.getexif.assert_not_called()

    def test_falls_back_to_datetime_when_original_absent(self):
        # Tag 306 (DateTime) is used when 36867 (DateTimeOriginal) is missing.
        img = self._make_img({306: "2024:06:01 08:00:00"})
        self.assertEqual(
            pfb.framebuffer._extract_exif_text(img, show_timestamp=True, show_model=False),
            "2024:06:01 08:00:00",
        )

    def test_prefers_datetime_original_over_datetime(self):
        img = self._make_img({36867: "2024:01:15 10:30:00", 306: "2024:01:01 00:00:00"})
        result = pfb.framebuffer._extract_exif_text(img, show_timestamp=True, show_model=False)
        self.assertIn("2024:01:15 10:30:00", result)

    def test_strips_whitespace_from_fields(self):
        img = self._make_img({272: "  Sony A7 IV  "})
        self.assertEqual(
            pfb.framebuffer._extract_exif_text(img, show_timestamp=False, show_model=True),
            "Sony A7 IV",
        )

    def test_no_relevant_tags_returns_none(self):
        img = self._make_img({271: "Canon"})  # Make only, no Model or DateTime
        self.assertIsNone(
            pfb.framebuffer._extract_exif_text(img, show_timestamp=True, show_model=True)
        )

    def test_empty_exif_returns_none(self):
        img = self._make_img({})
        self.assertIsNone(
            pfb.framebuffer._extract_exif_text(img, show_timestamp=True, show_model=True)
        )

    def test_getexif_exception_returns_none(self):
        # If EXIF cannot be read at all, None must be returned without raising.
        img = unittest.mock.MagicMock(spec=PIL.Image.Image)
        img.getexif.side_effect = Exception("no exif")
        self.assertIsNone(
            pfb.framebuffer._extract_exif_text(img, show_timestamp=True, show_model=True)
        )


class TestOverlayText(unittest.TestCase):
    def test_image_size_unchanged(self):
        # Overlaying text must not change the image dimensions.
        img = PIL.Image.new("RGB", (200, 100), (0, 0, 0))
        result = pfb.framebuffer._overlay_text(img, "2024:01:15  Canon EOS R5")
        self.assertEqual(result.size, (200, 100))

    def test_bottom_left_pixels_modified(self):
        # The bottom-left area must differ from a plain black image after overlay.
        plain = PIL.Image.new("RGB", (400, 200), (0, 0, 0))
        overlaid = PIL.Image.new("RGB", (400, 200), (0, 0, 0))
        pfb.framebuffer._overlay_text(overlaid, "Hello")
        self.assertNotEqual(numpy.array(plain).tolist(), numpy.array(overlaid).tolist())


class TestDisplayImage(unittest.TestCase):
    def test_seeks_to_zero_before_write(self):
        # display_image must seek to offset 0 before writing so prior content is overwritten.
        fb, mock_libpyfb_fb = _make_fb(2, 2, 32)
        with unittest.mock.patch("PIL.Image.open", return_value=PIL.Image.new("RGB", (2, 2))):
            fb.display_image("/fake/image.jpg")
        mock_libpyfb_fb.fb.seek.assert_called_once_with(0)

    def test_write_called_once(self):
        fb, mock_libpyfb_fb = _make_fb(2, 2, 32)
        with unittest.mock.patch("PIL.Image.open", return_value=PIL.Image.new("RGB", (2, 2))):
            fb.display_image("/fake/image.jpg")
        mock_libpyfb_fb.fb.write.assert_called_once()

    def test_written_data_length_32bpp(self):
        # For a 4×3 screen at 32 bpp, exactly 48 bytes must be written.
        fb, mock_libpyfb_fb = _make_fb(4, 3, 32)
        with unittest.mock.patch("PIL.Image.open", return_value=PIL.Image.new("RGB", (4, 3))):
            fb.display_image("/fake/image.jpg")
        written = mock_libpyfb_fb.fb.write.call_args[0][0]
        self.assertEqual(len(written), 48)

    def test_written_data_length_16bpp(self):
        # For a 4×3 screen at 16 bpp, exactly 24 bytes must be written.
        fb, mock_libpyfb_fb = _make_fb(4, 3, 16)
        with unittest.mock.patch("PIL.Image.open", return_value=PIL.Image.new("RGB", (4, 3))):
            fb.display_image("/fake/image.jpg")
        written = mock_libpyfb_fb.fb.write.call_args[0][0]
        self.assertEqual(len(written), 24)

    def test_exif_overlay_called_when_flag_given(self):
        # _overlay_text must be called when show_model=True and EXIF has the field.
        fb, mock_libpyfb_fb = _make_fb(100, 100, 32)
        mock_img = PIL.Image.new("RGB", (100, 100))
        mock_img.getexif = lambda: {272: "Canon EOS R5"}
        with unittest.mock.patch("PIL.Image.open", return_value=mock_img):
            with unittest.mock.patch("pfb.framebuffer._overlay_text", wraps=pfb.framebuffer._overlay_text) as mock_overlay:
                fb.display_image("/fake/image.jpg", show_model=True)
        mock_overlay.assert_called_once()

    def test_exif_overlay_not_called_without_flags(self):
        # _overlay_text must not be called when neither show_timestamp nor show_model is set.
        fb, mock_libpyfb_fb = _make_fb(100, 100, 32)
        mock_img = PIL.Image.new("RGB", (100, 100))
        mock_img.getexif = lambda: {272: "Canon EOS R5"}
        with unittest.mock.patch("PIL.Image.open", return_value=mock_img):
            with unittest.mock.patch("pfb.framebuffer._overlay_text") as mock_overlay:
                fb.display_image("/fake/image.jpg")
        mock_overlay.assert_not_called()


if __name__ == "__main__":
    unittest.main()
