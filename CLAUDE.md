# photoframebuffer

Python package for displaying images on a Linux framebuffer device.

## Package

Principal package: `pfb`

## Structure

```
pfb/
  libpyfb.py          # vendored libpyfb (raspiduino/libpyfb)
  framebuffer.py      # Framebuffer class wrapping libpyfb
  entrypoints/        # one module per console script
    show.py           # pfb_show
    slideshow.py      # pfb_slideshow
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
| `pfb_show <device> <image>` | Display a single image |
| `pfb_slideshow <device> <source> [--filter PATTERN] [--time SECONDS] [--root PATH]` | Slideshow from a directory or file list |

`<source>` for `pfb_slideshow` is either a directory path or a text file with one image path per line.

## Conventions

- All console script entry points live in `pfb/entrypoints/`
- Framebuffer writes go through `pfb.framebuffer.Framebuffer`, which uses libpyfb internally
- libpyfb lives at `pfb/libpyfb.py` and is imported as `from pfb import libpyfb`

## Install

```
pip install -e .
```

## Dependencies

- Pillow
- numpy
