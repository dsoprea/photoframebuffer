"""Framebuffer display support via libpyfb."""

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

# Font size for the EXIF overlay, and candidate system font paths to try in order.
_OVERLAY_FONT_SIZE = 20
_OVERLAY_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]


def _load_font() -> PIL.ImageFont.FreeTypeFont | PIL.ImageFont.ImageFont:
    # Try each candidate path and return the first truetype font that loads.
    for path in _OVERLAY_FONT_CANDIDATES:
        try:
            return PIL.ImageFont.truetype(path, _OVERLAY_FONT_SIZE)
        except (IOError, OSError):
            continue
    # Fall back to the built-in bitmap font if no truetype font is available.
    return PIL.ImageFont.load_default()


def _extract_exif_text(img: PIL.Image.Image) -> str | None:
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

    # Build the overlay string: timestamp left of model when both are present.
    if timestamp and model:
        return f"{timestamp}  {model}"
    if timestamp:
        return timestamp
    if model:
        return model
    return None


def _overlay_text(img: PIL.Image.Image, text: str) -> PIL.Image.Image:
    draw = PIL.ImageDraw.Draw(img)
    font = _load_font()

    # Measure the rendered text to find the bottom-right anchor position.
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = img.width - text_w - _OVERLAY_PADDING
    y = img.height - text_h - _OVERLAY_PADDING

    # Draw a dark outline around each character for legibility on any background.
    for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))

    # Draw the white foreground text.
    draw.text((x, y), text, font=font, fill=(255, 255, 255))

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

    def _fit_image(self, img: PIL.Image.Image) -> PIL.Image.Image:
        # Normalise to RGB so downstream encoding always operates on 3 channels.
        img = img.convert("RGB")

        # Shrink the image to fit within screen bounds, preserving aspect ratio.
        img.thumbnail((self.width, self.height), PIL.Image.LANCZOS)

        # Centre the scaled image on a black canvas that exactly matches the screen size.
        canvas = PIL.Image.new("RGB", (self.width, self.height), (0, 0, 0))
        x = (self.width - img.width) // 2
        y = (self.height - img.height) // 2
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

    def display_image(self, path: str) -> None:
        img = PIL.Image.open(path)

        # Extract EXIF text before _fit_image converts the image (which may drop EXIF).
        exif_text = _extract_exif_text(img)

        # Scale and centre the image to fill the screen.
        img = self._fit_image(img)

        # Overlay EXIF metadata in the bottom-right corner if any was found.
        if exif_text:
            img = _overlay_text(img, exif_text)

        # Encode to raw framebuffer bytes and write to the memory-mapped device.
        data = self._encode(img)
        self._fb.fb.seek(0)
        self._fb.fb.write(data)
