#!/usr/bin/env python3
"""Crop image-generation letterboxing to the chroma-key sheet region."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def parse_hex_color(value: str) -> tuple[int, int, int]:
    value = value.removeprefix("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("color must be #RRGGBB")
    try:
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError as error:
        raise argparse.ArgumentTypeError("color must be #RRGGBB") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--key-color",
        type=parse_hex_color,
        default=parse_hex_color("#ff00ff"),
    )
    parser.add_argument("--tolerance", type=int, default=48)
    parser.add_argument("--padding", type=int, default=0)
    args = parser.parse_args()

    image = Image.open(args.input).convert("RGBA")
    key_r, key_g, key_b = args.key_color
    tolerance_squared = args.tolerance * args.tolerance
    key_mask = Image.new("1", image.size)
    key_mask.putdata(
        [
            (
                (red - key_r) ** 2
                + (green - key_g) ** 2
                + (blue - key_b) ** 2
            )
            <= tolerance_squared
        for red, green, blue, _alpha in image.get_flattened_data()
        ]
    )
    bbox = key_mask.getbbox()
    if bbox is None:
        raise ValueError("No chroma-key sheet region found")
    left, top, right, bottom = bbox
    padding = max(0, args.padding)
    crop = (
        max(0, left - padding),
        max(0, top - padding),
        min(image.width, right + padding),
        min(image.height, bottom + padding),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.crop(crop).save(args.output, optimize=True)
    print(
        f"Wrote {args.output}: source={image.width}x{image.height}, "
        f"key_bbox={bbox}, crop={crop}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
