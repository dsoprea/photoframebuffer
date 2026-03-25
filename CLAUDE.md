# photoframebuffer

Python package for displaying images on a Linux framebuffer device.

## Package

Principal package: `pfb`

## Structure

```
pfb/
  libpyfb.py          # vendored libpyfb (raspiduino/libpyfb)
  framebuffer.py      # Framebuffer class, EXIF overlay helpers
  entrypoints/        # one module per console script
    show.py           # pfb_show
    slideshow.py      # pfb_slideshow
tests/
  test_framebuffer.py
  test_show.py
  test_slideshow.py
```

## Script Argument Style

Required parameters are positional arguments. Optional flags use `--flag` style.

---

## Script Output Style

Print labels and values with a plain colon and single space — no padding to align
columns (e.g. `"Position: {:.4f} in"`, not `"Position      : {:.4f} in"`).

Scripts that display multi-row tabular data (e.g. `settings_list`) use dynamic
column widths so that columns align across rows. Header and separator rows are
included.

---

## Import Style

All imports use `import X` or `import X.Y` — never `from X import Y`. Reference
symbols by their full dotted path (e.g. `tigerstop.adapter.TigerStop`,
`unittest.mock.patch`).

`__init__.py` files are empty — no re-exports, no code.

---

## Scripts

| Command | Description |
|---|---|
| `pfb_show <device> <image> [--timestamp] [--model]` | Display a single image |
| `pfb_slideshow <device> <source> [--filter PATTERN] [--time SECONDS] [--root PATH] [--random] [--timestamp] [--model]` | Slideshow from a directory or file list |

`<source>` for `pfb_slideshow` is either a directory path or a text file with one image path per line.

`--timestamp` overlays the EXIF timestamp in the bottom-left corner. `--model` overlays the EXIF camera model. When both are given, timestamp appears to the left of model.

During a slideshow, the left arrow key goes to the previous image and the right arrow key skips to the next. Images also advance automatically after `--time` seconds with no key press.

The slideshow loops indefinitely. When the list is exhausted it restarts from the beginning; if `--random` was given the list is reshuffled before each loop.

## Conventions

- All console script entry points live in `pfb/entrypoints/`
- Framebuffer writes go through `pfb.framebuffer.Framebuffer`, which uses libpyfb internally
- libpyfb lives at `pfb/libpyfb.py` and is imported as `import pfb.libpyfb`
- Every logical block of code must have a comment

## Tests

Run with:

```
python -m unittest discover -v tests/
```

Tests mock `pfb.libpyfb.Framebuffer` to avoid requiring real hardware.

## Install

```
pip install -e .
```

`pyproject.toml` explicitly lists packages under `[tool.setuptools]`:

```toml
[tool.setuptools]
packages = ["pfb", "pfb.entrypoints"]
```

## Dependencies

- Pillow
- numpy
