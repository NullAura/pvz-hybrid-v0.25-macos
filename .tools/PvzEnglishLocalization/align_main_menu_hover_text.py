#!/usr/bin/env python3
"""Build a hover layer that exactly follows the normal-state label geometry."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


DEFAULT_TEXT_REGION = (42, 35, 169, 123)


def text_mask(
    image: Image.Image,
    region: tuple[int, int, int, int],
) -> Image.Image:
    """Extract the blue-gray English label without including the sign border."""

    rgba = image.convert("RGBA")
    pixels = rgba.load()
    mask = Image.new("L", rgba.size, 0)
    output = mask.load()
    left, top, right, bottom = region
    for y in range(top, bottom):
        for x in range(left, right):
            red, green, blue, alpha = pixels[x, y]
            chroma = 2 * blue - red - green
            # The label face is a muted blue-gray. The sign frame is a much
            # more saturated royal blue, while the panel is nearly neutral.
            # Keeping only the middle band isolates the existing letterforms.
            if not (
                45 <= red < 120
                and 75 <= green < 145
                and 115 <= blue < 185
                and 60 < chroma < 175
            ):
                continue
            coverage = max(0, min(255, round((chroma - 60) * 255 / 42)))
            output[x, y] = min(alpha, coverage)

    # Remove isolated antialiasing noise while retaining the hand-painted edge.
    mask = mask.filter(ImageFilter.MedianFilter(3))
    if mask.getbbox() is None:
        raise ValueError("Unable to find the normal-state English label")
    return mask


def colorized_layer(mask: Image.Image) -> Image.Image:
    """Recreate the original white/blue hover treatment on the exact mask."""

    canvas = Image.new("RGBA", mask.size, (0, 0, 0, 0))

    broad_glow = mask.filter(ImageFilter.GaussianBlur(7.0))
    broad_glow = broad_glow.point(lambda value: round(value * 0.42))
    glow_layer = Image.new("RGBA", mask.size, (232, 255, 181, 0))
    glow_layer.putalpha(broad_glow)
    canvas = Image.alpha_composite(canvas, glow_layer)

    rim_mask = mask.filter(ImageFilter.MaxFilter(3))
    rim_mask = ImageChops.subtract(rim_mask, mask)
    rim_layer = Image.new("RGBA", mask.size, (55, 101, 224, 0))
    rim_layer.putalpha(rim_mask.point(lambda value: round(value * 0.82)))
    canvas = Image.alpha_composite(canvas, rim_layer)

    face = Image.new("RGBA", mask.size, (250, 250, 242, 0))
    face.putalpha(mask)
    canvas = Image.alpha_composite(canvas, face)

    soft_highlight = mask.filter(ImageFilter.GaussianBlur(0.6))
    soft_highlight = ImageChops.subtract(soft_highlight, mask)
    highlight_layer = Image.new("RGBA", mask.size, (134, 167, 255, 0))
    highlight_layer.putalpha(soft_highlight)
    return Image.alpha_composite(canvas, highlight_layer)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--normal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", type=Path)
    parser.add_argument(
        "--region",
        nargs=4,
        type=int,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        default=DEFAULT_TEXT_REGION,
    )
    args = parser.parse_args()

    normal = Image.open(args.normal).convert("RGBA")
    mask = text_mask(normal, tuple(args.region))
    layer = colorized_layer(mask)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    layer.save(args.output, optimize=True)

    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        Image.alpha_composite(normal, layer).save(args.preview, optimize=True)

    print(
        f"Wrote aligned hover layer: canvas={normal.width}x{normal.height} "
        f"text_bbox={mask.getbbox()} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
