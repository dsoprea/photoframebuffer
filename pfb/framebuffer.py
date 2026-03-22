"""Framebuffer display support via libpyfb."""

import numpy
import PIL.Image

import pfb.libpyfb


class Framebuffer:
    def __init__(self, device: str) -> None:
        self._fb = pfb.libpyfb.Framebuffer(device)

    @property
    def width(self) -> int:
        return self._fb.screenx

    @property
    def height(self) -> int:
        return self._fb.screeny

    def _fit_image(self, img: PIL.Image.Image) -> PIL.Image.Image:
        """Scale image to fill the screen, preserving aspect ratio, black-padded."""
        img = img.convert("RGB")
        img.thumbnail((self.width, self.height), PIL.Image.LANCZOS)
        canvas = PIL.Image.new("RGB", (self.width, self.height), (0, 0, 0))
        x = (self.width - img.width) // 2
        y = (self.height - img.height) // 2
        canvas.paste(img, (x, y))
        return canvas

    def _encode(self, img: PIL.Image.Image) -> bytes:
        arr = numpy.array(img, dtype=numpy.uint8)
        if self._fb.bpp == 32:
            # libpyfb writes pixels as B, G, R, T
            out = numpy.zeros((self.height, self.width, 4), dtype=numpy.uint8)
            out[:, :, 0] = arr[:, :, 2]  # B
            out[:, :, 1] = arr[:, :, 1]  # G
            out[:, :, 2] = arr[:, :, 0]  # R
            return out.tobytes()
        else:
            # RGB565
            r = arr[:, :, 0].astype(numpy.uint16)
            g = arr[:, :, 1].astype(numpy.uint16)
            b = arr[:, :, 2].astype(numpy.uint16)
            pixels = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            return pixels.tobytes()

    def display_image(self, path: str) -> None:
        img = PIL.Image.open(path)
        img = self._fit_image(img)
        data = self._encode(img)
        self._fb.fb.seek(0)
        self._fb.fb.write(data)
