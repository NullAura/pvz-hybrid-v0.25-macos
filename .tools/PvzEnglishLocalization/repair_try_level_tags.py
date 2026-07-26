#!/usr/bin/env python3
"""Restore the original tab states and transfer only generated English ink."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


TAG_PATHS = (
    "TryLevel/TryLevelTagPurple.png",
    "TryLevel/TryLevelTagPurpleUnselected.png",
    "TryLevel/TryLevelTagRainbow.png",
    "TryLevel/TryLevelTagRainbowUnselected.png",
    "TryLevel/TryLevelTagStar.png",
    "TryLevel/TryLevelTagStarUnselected.png",
)


def neutral_white_mask(
    image: Image.Image,
    *,
    top: int,
    bottom: int,
    threshold: int,
) -> Image.Image:
    """Select white lettering, then grow through its dark hand-drawn stroke."""
    rgba = image.convert("RGBA")
    width, height = rgba.size
    values: list[int] = []
    for index, (red, green, blue, alpha) in enumerate(
        rgba.get_flattened_data()
    ):
        x = index % width
        y = index // width
        is_ink = (
            3 <= x < width - 3
            and top <= y < min(bottom, height)
            and min(red, green, blue) >= threshold
            and max(red, green, blue) - min(red, green, blue) <= 70
        )
        values.append(alpha if is_ink else 0)
    mask = Image.new("L", rgba.size)
    mask.putdata(values)
    return mask.filter(ImageFilter.MaxFilter(7)).filter(
        ImageFilter.GaussianBlur(0.35)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--blank-root", type=Path, required=True)
    parser.add_argument("--localized-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    for relative_text in TAG_PATHS:
        relative = Path(relative_text)
        original = Image.open(
            args.original_root / relative
        ).convert("RGBA")
        blank = Image.open(args.blank_root / relative).convert("RGBA")
        source_relative = relative
        if relative.name == "TryLevelTagPurpleUnselected.png":
            source_relative = Path("TryLevel/TryLevelTagPurple.png")
        english = Image.open(
            args.localized_root / source_relative
        ).convert("RGBA")
        if not (
            original.size == blank.size == english.size
        ):
            raise ValueError(
                f"canvas mismatch for {relative}: "
                f"{original.size}, {blank.size}, {english.size}"
            )

        chinese_mask = neutral_white_mask(
            original,
            top=55,
            bottom=150,
            threshold=210,
        )
        cleaned = Image.composite(blank, original, chinese_mask)

        english_mask = neutral_white_mask(
            english,
            top=25,
            bottom=155,
            threshold=220,
        )
        # Never restore generated background pixels outside the irregular
        # white-letter-plus-black-stroke mask.
        english_layer = english.copy()
        english_layer.putalpha(
            ImageChops.multiply(
                english.getchannel("A"),
                english_mask,
            )
        )
        result = Image.alpha_composite(cleaned, english_layer)
        destination = args.output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        result.save(destination, optimize=True)

    print(
        "Repaired TryLevel tags: "
        f"files={len(TAG_PATHS)} original_states=preserved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
