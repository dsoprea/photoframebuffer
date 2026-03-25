"""pfb_slideshow entry point."""

import argparse
import fnmatch
import os
import pathlib
import random
import select
import sys
import termios
import time
import tty

import pfb.framebuffer

# Escape sequences produced by the left and right arrow keys (ANSI VT100).
_KEY_LEFT = b"\x1b[D"
_KEY_RIGHT = b"\x1b[C"


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


def _read_key(timeout: float) -> str | None:
    """Wait up to timeout seconds for a key press in raw terminal mode.

    Returns 'left', 'right', or None on timeout or unrecognised key.
    Must be called with the terminal already in raw mode.
    Uses os.read() on the raw fd to bypass Python's buffered text-mode stdin.
    """
    fd = sys.stdin.fileno()

    # Wait for stdin to become readable within the timeout period.
    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        return None

    # Read the first byte of the key sequence.
    ch = os.read(fd, 1)

    # Arrow keys send a 3-byte escape sequence: ESC [ <letter>.
    # Read the remaining two bytes one at a time with short timeouts.
    if ch == b"\x1b":
        ready, _, _ = select.select([fd], [], [], 0.05)
        if ready:
            ch += os.read(fd, 1)
            ready, _, _ = select.select([fd], [], [], 0.05)
            if ready:
                ch += os.read(fd, 1)

    # Map recognised sequences to logical key names.
    if ch == _KEY_LEFT:
        return "left"
    if ch == _KEY_RIGHT:
        return "right"
    return None


def _wait_for_key(timeout: float) -> str | None:
    """Wait up to timeout seconds for a navigation key.

    Puts the terminal in raw mode if stdin is a tty; otherwise falls back to
    a plain sleep and returns None.
    """
    # Raw mode requires an interactive terminal — fall back to sleep otherwise.
    if not os.isatty(sys.stdin.fileno()):
        time.sleep(timeout)
        return None

    # Save terminal state, switch to raw mode, then restore on exit.
    old_term = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin.fileno())
        return _read_key(timeout)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_term)


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

    # Open the framebuffer device once for the duration of the slideshow.
    fb = pfb.framebuffer.Framebuffer(args.device)

    # Iterate by index so left/right keys can move backwards and forwards.
    index = 0
    while True:
        # When the end of the list is reached, reshuffle if requested and loop.
        if index >= len(files):
            if args.random:
                random.shuffle(files)
            index = 0

        path = files[index]
        print(f"displaying: {path}")
        try:
            fb.display_image(path, show_timestamp=args.timestamp, show_model=args.model)
        except Exception as exc:
            print(f"pfb_slideshow: skipping {path}: {exc}", file=sys.stderr)
            index += 1
            continue

        # Wait for a navigation key or the display timeout.
        key = _wait_for_key(args.time)

        # Left moves to the previous image; right or timeout advances to the next.
        if key == "left":
            index = max(0, index - 1)
        elif key == "right" or key is None:
            index += 1
