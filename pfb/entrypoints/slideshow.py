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

# DECTCEM: hide / show the hardware text cursor on VT-style consoles (linux framebuffer tty).
_CURSOR_HIDE = b"\x1b[?25l"
_CURSOR_SHOW = b"\x1b[?25h"


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


def _choose_cursor_tty_fd() -> int | None:
    # Use stdout first, then stderr, when either is a tty (same console as the blinking cursor).
    for stream in (sys.stdout, sys.stderr):
        try:
            fd = stream.fileno()
        except (ValueError, OSError):
            continue
        if os.isatty(fd):
            return fd
    return None


def _tty_cursor_set_visible(fd: int, visible: bool) -> None:
    # Apply DECTCEM via raw write; ignore errors on pipes or consoles that ignore the sequence.
    seq = _CURSOR_SHOW if visible else _CURSOR_HIDE
    try:
        os.write(fd, seq)
    except OSError:
        pass


def _read_key(timeout: float) -> str | None:
    """Wait up to timeout seconds for a key press in raw terminal mode.

    Returns 'left', 'right', 'quit' (Escape alone), or None on timeout or unrecognised key.
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
    # Lone ESC (or Ctrl+[) quits; arrow keys are longer sequences handled above.
    if ch == b"\x1b":
        return "quit"
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

    args = parser.parse_args()

    # Resolve the list of files to display, applying filter and root as needed.
    files = _collect_files(args.source, args.filter_pattern, args.root)
    if not files:
        print("pfb_slideshow: no files found", file=sys.stderr)
        sys.exit(1)

    cursor_tty_fd = _choose_cursor_tty_fd()

    try:
        # Hide the console cursor so it does not blink over the framebuffer image.
        if cursor_tty_fd is not None:
            _tty_cursor_set_visible(cursor_tty_fd, visible=False)

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
                fb.display_image(path, slideshow_gutter=True)
            except Exception as exc:
                print(f"pfb_slideshow: skipping {path}: {exc}", file=sys.stderr)
                index += 1
                continue

            # Wait for a navigation key or the display timeout.
            key = _wait_for_key(args.time)

            # Left moves to the previous image; right or timeout advances to the next.
            if key == "left":
                index = max(0, index - 1)
            elif key == "quit":
                fb.clear()
                sys.exit(0)
            elif key == "right" or key is None:
                index += 1
    finally:
        # Always restore the cursor after slideshow ends or aborts.
        if cursor_tty_fd is not None:
            _tty_cursor_set_visible(cursor_tty_fd, visible=True)
