"""Tests for pfb.entrypoints.show."""

import unittest
import unittest.mock

import pfb.entrypoints.show


class TestShowMain(unittest.TestCase):
    def test_opens_framebuffer_with_given_device(self):
        mock_fb = unittest.mock.MagicMock()
        with unittest.mock.patch("sys.argv", ["pfb_show", "/dev/fb0", "/img.jpg"]):
            with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb) as mock_cls:
                pfb.entrypoints.show.main()
        mock_cls.assert_called_once_with("/dev/fb0")

    def test_calls_display_image_with_given_path(self):
        mock_fb = unittest.mock.MagicMock()
        with unittest.mock.patch("sys.argv", ["pfb_show", "/dev/fb0", "/path/to/image.jpg"]):
            with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb):
                pfb.entrypoints.show.main()
        mock_fb.display_image.assert_called_once_with("/path/to/image.jpg")


if __name__ == "__main__":
    unittest.main()
