"""pfb_slideshow entry point."""

import argparse
import fnmatch
import pathlib
import sys
import time

import pfb.framebuffer


def _collect_files(source: str, filter_pattern: str | None, root: str | None) -> list[str]:
    source_path = pathlib.Path(source)

    if source_path.is_dir():
        files = sorted(str(f) for f in source_path.iterdir() if f.is_file())
    else:
        with open(source_path) as fh:
            files = [line.strip() for line in fh if line.strip()]
        if root:
            root_path = pathlib.Path(root)
            files = [str(root_path / f) for f in files]

    if filter_pattern:
        files = [f for f in files if fnmatch.fnmatch(pathlib.Path(f).name, filter_pattern)]

    return files


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pfb_slideshow",
        description="Display images on a Linux framebuffer device.",
    )
    parser.add_argument("device", help="Framebuffer device (e.g. /dev/fb0)")
    parser.add_argument(
        "source",
        help="Directory to list images from, or a text file containing one image path per line",
    )
    parser.add_argument(
        "--filter",
        metavar="PATTERN",
        dest="filter_pattern",
        help="fnmatch pattern applied to filenames (e.g. '*.jpg')",
    )
    parser.add_argument(
        "--time",
        type=float,
        default=300.0,
        metavar="SECONDS",
        help="Seconds to display each image (default: 300)",
    )
    parser.add_argument(
        "--root",
        metavar="PATH",
        help="Root path prepended to relative paths read from a file list",
    )

    args = parser.parse_args()

    files = _collect_files(args.source, args.filter_pattern, args.root)
    if not files:
        print("pfb_slideshow: no files found", file=sys.stderr)
        sys.exit(1)

    fb = pfb.framebuffer.Framebuffer(args.device)

    for path in files:
        print(f"displaying: {path}")
        try:
            fb.display_image(path)
        except Exception as exc:
            print(f"pfb_slideshow: skipping {path}: {exc}", file=sys.stderr)
            continue
        time.sleep(args.time)
