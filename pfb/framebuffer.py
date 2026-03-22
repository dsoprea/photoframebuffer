"""Framebuffer display support via libpyfb."""

import numpy
import PIL.Image

import pfb.libpyfb


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
        # Load and scale the image to fit the screen.
        img = PIL.Image.open(path)
        img = self._fit_image(img)

        # Encode to raw framebuffer bytes and write to the memory-mapped device.
        data = self._encode(img)
        self._fb.fb.seek(0)
        self._fb.fb.write(data)
