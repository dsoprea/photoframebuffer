"""pfb_slideshow entry point."""

import argparse
import fnmatch
import pathlib
import random
import sys
import time

import pfb.framebuffer


def _collect_files(source: str, filter_pattern: str | None, root: str | None) -> list[str]:
    source_path = pathlib.Path(source)

    # If source is a directory, list all files in it sorted by name.
    # Otherwise treat it as a text file with one image path per line.
    if source_path.is_dir():
        files = sorted(str(f) for f in source_path.iterdir() if f.is_file())
    else:
        with open(source_path) as fh:
            files = [line.strip() for line in fh if line.strip()]

        # Prepend root to make relative paths absolute when a root is given.
        if root:
            root_path = pathlib.Path(root)
            files = [str(root_path / f) for f in files]

    # Apply optional fnmatch filter against the filename component only.
    if filter_pattern:
        files = [f for f in files if fnmatch.fnmatch(pathlib.Path(f).name, filter_pattern)]

    return files


def main() -> None:
    # Define CLI arguments.
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
    parser.add_argument(
        "--random",
        action="store_true",
        help="Display images in random order",
    )
    parser.add_argument(
        "--timestamp",
        action="store_true",
        help="Overlay the EXIF timestamp in the bottom-left corner",
    )
    parser.add_argument(
        "--model",
        action="store_true",
        help="Overlay the EXIF camera model in the bottom-left corner",
    )

    args = parser.parse_args()

    # Resolve the list of files to display, applying filter and root as needed.
    files = _collect_files(args.source, args.filter_pattern, args.root)
    if not files:
        print("pfb_slideshow: no files found", file=sys.stderr)
        sys.exit(1)

    # Shuffle the file list when random order is requested.
    if args.random:
        random.shuffle(files)

    # Open the framebuffer device once and display each image in turn.
    fb = pfb.framebuffer.Framebuffer(args.device)

    for path in files:
        print(f"displaying: {path}")
        try:
            fb.display_image(path, show_timestamp=args.timestamp, show_model=args.model)
        except Exception as exc:
            print(f"pfb_slideshow: skipping {path}: {exc}", file=sys.stderr)
            continue
        # Hold the image on screen for the configured duration.
        time.sleep(args.time)
