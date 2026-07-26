#!/usr/bin/env python3
"""Fit a transparent image-generation result into an original texture canvas."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def alpha_bbox(image: Image.Image, threshold: int) -> tuple[int, int, int, int]:
    alpha = image.convert("RGBA").getchannel("A")
    mask = alpha.point(lambda value: 255 if value >= threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        raise ValueError("Image has no visible pixels above the alpha threshold")
    return bbox


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=int, default=32)
    args = parser.parse_args()

    generated = Image.open(args.generated).convert("RGBA")
    original = Image.open(args.original).convert("RGBA")
    generated_bbox = alpha_bbox(generated, args.threshold)
    target_bbox = alpha_bbox(original, args.threshold)
    subject = generated.crop(generated_bbox)

    target_width = target_bbox[2] - target_bbox[0]
    target_height = target_bbox[3] - target_bbox[1]
    scale = min(target_width / subject.width, target_height / subject.height)
    fitted_size = (
        max(1, round(subject.width * scale)),
        max(1, round(subject.height * scale)),
    )
    subject = subject.resize(fitted_size, Image.Resampling.LANCZOS)
    left = target_bbox[0] + (target_width - fitted_size[0]) // 2
    top = target_bbox[1] + (target_height - fitted_size[1]) // 2
    canvas = Image.new("RGBA", original.size, (0, 0, 0, 0))
    canvas.alpha_composite(subject, (left, top))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, optimize=True)
    print(
        f"Wrote {args.output}: canvas={original.width}x{original.height}, "
        f"target_bbox={target_bbox}, generated_bbox={generated_bbox}, "
        f"fitted={fitted_size[0]}x{fitted_size[1]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
