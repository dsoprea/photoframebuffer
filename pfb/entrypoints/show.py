"""pfb_show entry point."""

import argparse

import pfb.framebuffer


def main() -> None:
    # Define CLI arguments.
    parser = argparse.ArgumentParser(
        prog="pfb_show",
        description="Display a single image on a Linux framebuffer device.",
    )
    parser.add_argument("device", help="Framebuffer device (e.g. /dev/fb0)")
    parser.add_argument("image", help="Path to the image file to display")

    args = parser.parse_args()

    # Open the framebuffer and display the image.
    pfb.framebuffer.Framebuffer(args.device).display_image(args.image)
