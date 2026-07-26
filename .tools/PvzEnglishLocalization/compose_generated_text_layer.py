#!/usr/bin/env python3
"""Composite only image-generated lettering onto an exact source texture."""

from __future__ import annotations

import argparse
import colorsys
from pathlib import Path

from PIL import Image, ImageFilter


def parse_box(value: str) -> tuple[int, int, int, int]:
    try:
        parts = tuple(int(part) for part in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "box must be x,y,width,height"
        ) from error
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise argparse.ArgumentTypeError("box must be x,y,width,height")
    return parts


def text_alpha(image: Image.Image, colors: str) -> Image.Image:
    """Select the blue and orange generated lettering without its backdrop."""
    rgba = image.convert("RGBA")
    alpha_values: list[int] = []
    for red, green, blue, source_alpha in rgba.get_flattened_data():
        hue, saturation, value = colorsys.rgb_to_hsv(
            red / 255, green / 255, blue / 255
        )
        cyan = 0.50 <= hue <= 0.66 and saturation >= 0.18
        orange = (
            (hue <= 0.16 or hue >= 0.98)
            and saturation >= 0.28
            and red >= green
        )
        if colors == "outlined":
            # Isolated lettering is returned on a light gray checkerboard.
            # Saturated fill and dark outline pixels are foreground; neutral
            # bright checker pixels (including letter counters) are removed.
            saturation_strength = (saturation - 0.015) / 0.11
            darkness_strength = (0.84 - value) / 0.32
            strength = max(saturation_strength, darkness_strength)
            alpha_values.append(
                round(source_alpha * max(0.0, min(1.0, strength)))
            )
            continue
        selected = (
            (colors in {"cyan", "both"} and cyan)
            or (colors in {"orange", "both"} and orange)
        )
        if not selected or value < 0.20:
            alpha_values.append(0)
            continue
        if cyan:
            strength = (saturation - 0.12) / 0.30
        else:
            strength = (saturation - 0.20) / 0.35
        alpha_values.append(
            round(source_alpha * max(0.0, min(1.0, strength)))
        )
    alpha = Image.new("L", rgba.size)
    alpha.putdata(alpha_values)
    return alpha.filter(ImageFilter.GaussianBlur(0.35))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-box", type=parse_box, required=True)
    parser.add_argument("--target-box", type=parse_box, required=True)
    parser.add_argument(
        "--colors",
        choices=("cyan", "orange", "both", "outlined"),
        default="both",
    )
    args = parser.parse_args()

    generated = Image.open(args.generated).convert("RGBA")
    base = Image.open(args.base).convert("RGBA")
    source_x, source_y, source_width, source_height = args.source_box
    target_x, target_y, target_width, target_height = args.target_box
    source = generated.crop(
        (
            source_x,
            source_y,
            source_x + source_width,
            source_y + source_height,
        )
    )
    alpha = text_alpha(source, args.colors)
    source.putalpha(alpha)
    source = source.resize(
        (target_width, target_height),
        Image.Resampling.LANCZOS,
    )
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.alpha_composite(source, (target_x, target_y))
    result = Image.alpha_composite(base, layer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.output, optimize=True)
    print(
        f"Wrote {args.output}: canvas={base.width}x{base.height} "
        f"source={args.source_box} target={args.target_box}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
