"""Framebuffer display support via libpyfb."""

import pathlib

import numpy
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont

import pfb.libpyfb

# EXIF tag IDs used for overlay text.
_EXIF_TAG_DATETIME_ORIGINAL = 36867  # DateTimeOriginal (preferred)
_EXIF_TAG_DATETIME = 306             # DateTime (fallback)
_EXIF_TAG_MODEL = 272                # Model

# Padding in pixels between the overlay text and the image edges.
_OVERLAY_PADDING = 10

# Vertical padding inside the slideshow footer gutter above and below the label text.
_GUTTER_VERTICAL_PADDING = 8

# Separator placed between filename, optional model, and optional timestamp in the gutter.
_GUTTER_SEGMENT_GAP = "    "

# Font size for the EXIF overlay, and candidate system font paths to try in order.
_OVERLAY_FONT_SIZE = 20
_OVERLAY_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]


def _load_font() -> PIL.ImageFont.FreeTypeFont | PIL.ImageFont.ImageFont:
    # Try each candidate path and return the first truetype font that loads.
    for font_path in _OVERLAY_FONT_CANDIDATES:
        try:
            return PIL.ImageFont.truetype(font_path, _OVERLAY_FONT_SIZE)
        except (IOError, OSError):
            continue
    # Fall back to the built-in bitmap font if no truetype font is available.
    return PIL.ImageFont.load_default()


def _extract_exif_text(
    img: PIL.Image.Image,
    show_timestamp: bool,
    show_model: bool,
) -> str | None:
    # Nothing requested — skip EXIF entirely.
    if not show_timestamp and not show_model:
        return None

    # Attempt to read the EXIF block; silently return None on any failure.
    try:
        exif = img.getexif()
    except Exception:
        return None

    if not exif:
        return None

    # Prefer DateTimeOriginal; fall back to DateTime if absent.
    timestamp = exif.get(_EXIF_TAG_DATETIME_ORIGINAL) or exif.get(_EXIF_TAG_DATETIME)
    model = exif.get(_EXIF_TAG_MODEL)

    # Strip surrounding whitespace that some cameras embed in string fields.
    if timestamp:
        timestamp = str(timestamp).strip()
    if model:
        model = str(model).strip()

    # Apply the caller's field selection.
    if not show_timestamp:
        timestamp = None
    if not show_model:
        model = None

    # Build the overlay string: timestamp left of model when both are present.
    if timestamp and model:
        return f"{timestamp}  {model}"
    if timestamp:
        return timestamp
    if model:
        return model
    return None


def _extract_exif_timestamp_model(img: PIL.Image.Image) -> tuple[str | None, str | None]:
    # Read timestamp and model independently for the slideshow gutter strip.
    try:
        exif = img.getexif()
    except Exception:
        return None, None

    if not exif:
        return None, None

    # Prefer DateTimeOriginal; fall back to DateTime if absent.
    timestamp = exif.get(_EXIF_TAG_DATETIME_ORIGINAL) or exif.get(_EXIF_TAG_DATETIME)
    model = exif.get(_EXIF_TAG_MODEL)

    # Strip surrounding whitespace that some cameras embed in string fields.
    if timestamp:
        timestamp = str(timestamp).strip()
    if model:
        model = str(model).strip()

    return timestamp or None, model or None


def _measure_text_height(font: PIL.ImageFont.FreeTypeFont | PIL.ImageFont.ImageFont) -> int:
    # Use a representative string so ascenders and descenders set the gutter height.
    probe = PIL.ImageDraw.Draw(PIL.Image.new("RGB", (1, 1)))
    bbox = probe.textbbox((0, 0), "Mg", font=font)
    return bbox[3] - bbox[1]


def _draw_white_outlined_text(
    draw: PIL.ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: PIL.ImageFont.FreeTypeFont | PIL.ImageFont.ImageFont,
) -> None:
    # Draw a dark outline around each character for legibility on any background.
    for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))

    # Draw the white foreground text.
    draw.text((x, y), text, font=font, fill=(255, 255, 255))


def _overlay_text(
    img: PIL.Image.Image,
    text: str,
    bottom_reserve: int = 0,
) -> PIL.Image.Image:
    draw = PIL.ImageDraw.Draw(img)
    font = _load_font()

    # Measure the rendered text to find the bottom-left anchor position.
    bbox = draw.textbbox((0, 0), text, font=font)
    text_h = bbox[3] - bbox[1]
    x = _OVERLAY_PADDING
    y = img.height - text_h - _OVERLAY_PADDING - bottom_reserve
    # Keep the overlay inside the image when the bottom is reserved for a gutter.
    y = max(_OVERLAY_PADDING, y)

    _draw_white_outlined_text(draw, x, y, text, font)

    return img


def _draw_slideshow_gutter(
    img: PIL.Image.Image,
    gutter_top_y: int,
    path: str,
    timestamp: str | None,
    model: str | None,
) -> PIL.Image.Image:
    draw = PIL.ImageDraw.Draw(img)
    font = _load_font()

    # Fill the footer band so it reads as a distinct strip below the photo.
    draw.rectangle([0, gutter_top_y, img.width, img.height], fill=(32, 32, 32))

    # Build one line: basename, then optional model, then optional timestamp.
    segments: list[str] = [pathlib.Path(path).name]
    if model:
        segments.append(model)
    if timestamp:
        segments.append(timestamp)
    line = _GUTTER_SEGMENT_GAP.join(segments)

    # Vertically centre the label within the gutter.
    bbox = draw.textbbox((0, 0), line, font=font)
    text_h = bbox[3] - bbox[1]
    x = _OVERLAY_PADDING
    y = gutter_top_y + max(0, (img.height - gutter_top_y - text_h) // 2)

    _draw_white_outlined_text(draw, x, y, line, font)

    return img


class Framebuffer:
    def __init__(self, device: str) -> None:
        # Open the framebuffer device via libpyfb, which reads screen geometry
        # and creates a memory-mapped view of the device.
        self._fb = pfb.libpyfb.Framebuffer(device)

    @property
    def width(self) -> int:
        return self._fb.screenx

    @property
    def height(self) -> int:
        return self._fb.screeny

    def _fit_image(
        self,
        img: PIL.Image.Image,
        viewport: tuple[int, int] | None = None,
    ) -> PIL.Image.Image:
        # Normalise to RGB so downstream encoding always operates on 3 channels.
        img = img.convert("RGB")

        # Use full framebuffer size unless a smaller viewport is supplied (e.g. above a gutter).
        vw, vh = viewport if viewport else (self.width, self.height)

        # Shrink the image to fit within the viewport bounds, preserving aspect ratio.
        img.thumbnail((vw, vh), PIL.Image.LANCZOS)

        # Centre the scaled image on a black canvas that matches the viewport size.
        canvas = PIL.Image.new("RGB", (vw, vh), (0, 0, 0))
        x = (vw - img.width) // 2
        y = (vh - img.height) // 2
        canvas.paste(img, (x, y))
        return canvas

    def _encode(self, img: PIL.Image.Image) -> bytes:
        # Convert image to a numpy array for vectorised pixel manipulation.
        arr = numpy.array(img, dtype=numpy.uint8)

        if self._fb.bpp == 32:
            # 32 bpp: libpyfb's drawpixel writes channels in B, G, R, T order.
            out = numpy.zeros((self.height, self.width, 4), dtype=numpy.uint8)
            out[:, :, 0] = arr[:, :, 2]  # B
            out[:, :, 1] = arr[:, :, 1]  # G
            out[:, :, 2] = arr[:, :, 0]  # R
            return out.tobytes()
        else:
            # 16 bpp: pack channels into RGB565 — 5 bits red, 6 bits green, 5 bits blue.
            r = arr[:, :, 0].astype(numpy.uint16)
            g = arr[:, :, 1].astype(numpy.uint16)
            b = arr[:, :, 2].astype(numpy.uint16)
            pixels = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            return pixels.tobytes()

    def display_image(
        self,
        path: str,
        show_timestamp: bool = False,
        show_model: bool = False,
        slideshow_gutter: bool = False,
    ) -> None:
        img = PIL.Image.open(path)

        # Extract EXIF text before _fit_image converts the image (which may drop EXIF).
        exif_text = _extract_exif_text(img, show_timestamp, show_model)

        # Reserve a footer strip for filename and optional EXIF fields during slideshows.
        gutter_h = 0
        ts_gutter: str | None = None
        model_gutter: str | None = None
        if slideshow_gutter:
            ts_gutter, model_gutter = _extract_exif_timestamp_model(img)
            font = _load_font()
            gutter_h = _measure_text_height(font) + 2 * _GUTTER_VERTICAL_PADDING
            gutter_h = min(gutter_h, max(1, self.height - 1))

        content_h = max(1, self.height - gutter_h)

        # Scale and centre the image within the drawable area above any gutter.
        img = self._fit_image(img, (self.width, content_h))

        # Paste into a full-screen canvas when a slideshow gutter is active.
        if slideshow_gutter:
            canvas = PIL.Image.new("RGB", (self.width, self.height), (0, 0, 0))
            canvas.paste(img, (0, 0))
            img = _draw_slideshow_gutter(canvas, content_h, path, ts_gutter, model_gutter)

        # Overlay EXIF metadata in the bottom-left corner if any was found.
        if exif_text:
            bottom_reserve = gutter_h if slideshow_gutter else 0
            img = _overlay_text(img, exif_text, bottom_reserve=bottom_reserve)

        # Encode to raw framebuffer bytes and write to the memory-mapped device.
        data = self._encode(img)
        self._fb.fb.seek(0)
        self._fb.fb.write(data)
