"""pfb_show entry point."""

import argparse

import pfb.framebuffer


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pfb_show",
        description="Display a single image on a Linux framebuffer device.",
    )
    parser.add_argument("device", help="Framebuffer device (e.g. /dev/fb0)")
    parser.add_argument("image", help="Path to the image file to display")

    args = parser.parse_args()

    pfb.framebuffer.Framebuffer(args.device).display_image(args.image)
