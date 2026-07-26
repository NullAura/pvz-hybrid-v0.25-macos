#!/usr/bin/env python3
"""Transfer only generated card lettering, never its rectangular backdrop."""

from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


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


def challenge_text_mask(image: Image.Image) -> Image.Image:
    """Extract cyan title and orange challenge lettering plus its ink stroke."""
    rgba = image.convert("RGBA")
    seed_values: list[int] = []
    color_data: list[tuple[float, float, float, int]] = []
    for red, green, blue, source_alpha in rgba.get_flattened_data():
        hue, saturation, value = colorsys.rgb_to_hsv(
            red / 255, green / 255, blue / 255
        )
        cyan = 0.48 <= hue <= 0.69 and saturation >= 0.28
        orange = (
            (hue <= 0.17 or hue >= 0.98)
            and saturation >= 0.34
            and red >= green
        )
        seed_values.append(255 if (cyan or orange) else 0)
        color_data.append((hue, saturation, value, source_alpha))
    seed = Image.new("L", rgba.size)
    seed.putdata(seed_values)
    proximity = seed.filter(ImageFilter.MaxFilter(7))
    proximity_values = proximity.get_flattened_data()
    output_values: list[int] = []
    for (
        (hue, saturation, value, source_alpha),
        seed_alpha,
        near_alpha,
    ) in zip(color_data, seed_values, proximity_values, strict=True):
        cyan_tint = 0.46 <= hue <= 0.72 and saturation >= 0.10
        orange_tint = (
            (hue <= 0.19 or hue >= 0.97) and saturation >= 0.12
        )
        dark_stroke = value <= 0.34
        pale_cyan_highlight = (
            value >= 0.68
            and saturation <= 0.30
            and 0.43 <= hue <= 0.75
        )
        candidate = (
            seed_alpha > 0
            or (
                near_alpha > 0
                and (
                    dark_stroke
                    or cyan_tint
                    or orange_tint
                    or pale_cyan_highlight
                )
            )
        )
        output_values.append(source_alpha if candidate else 0)
    mask = Image.new("L", rgba.size)
    mask.putdata(output_values)
    return mask.filter(ImageFilter.GaussianBlur(0.25))


def green_text_mask(
    image: Image.Image,
    include_white: bool,
    include_cream: bool,
) -> Image.Image:
    """Extract green level lettering and its dark game-logo stroke."""
    rgba = image.convert("RGBA")
    seed_values: list[int] = []
    color_data: list[tuple[float, float, float, int]] = []
    for red, green, blue, source_alpha in rgba.get_flattened_data():
        hue, saturation, value = colorsys.rgb_to_hsv(
            red / 255, green / 255, blue / 255
        )
        green_fill = 0.16 <= hue <= 0.48 and saturation >= 0.22
        cream_fill = (
            include_cream
            and 0.08 <= hue <= 0.22
            and saturation >= 0.05
            and value >= 0.45
        )
        white_fill = (
            include_white and value >= 0.72 and saturation <= 0.20
        )
        seed_values.append(
            255 if (green_fill or cream_fill or white_fill) else 0
        )
        color_data.append((hue, saturation, value, source_alpha))
    seed = Image.new("L", rgba.size)
    seed.putdata(seed_values)
    proximity = seed.filter(ImageFilter.MaxFilter(7))
    output_values: list[int] = []
    for (
        (hue, saturation, value, source_alpha),
        seed_alpha,
        near_alpha,
    ) in zip(
        color_data,
        seed_values,
        proximity.get_flattened_data(),
        strict=True,
    ):
        green_tint = 0.14 <= hue <= 0.50 and saturation >= 0.08
        cream_tint = (
            include_cream
            and 0.07 <= hue <= 0.23
            and value >= 0.34
            and saturation >= 0.03
        )
        dark_stroke = value <= 0.34
        candidate = (
            seed_alpha > 0
            or (
                near_alpha > 0
                and (dark_stroke or green_tint or cream_tint)
            )
        )
        output_values.append(source_alpha if candidate else 0)
    mask = Image.new("L", rgba.size)
    mask.putdata(output_values)
    return mask.filter(ImageFilter.GaussianBlur(0.25))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--localized-root", type=Path, required=True)
    parser.add_argument("--clean-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--source-box",
        type=parse_box,
        default=parse_box("180,40,210,110"),
    )
    parser.add_argument(
        "--mode",
        choices=("challenge", "green"),
        default="challenge",
    )
    parser.add_argument(
        "--ocr-report",
        type=Path,
        help="All-text OCR report used to exclude source-text remnants.",
    )
    parser.add_argument(
        "--path-contains",
        help="Process only records whose relative path contains this text.",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        help="Per-card include/exclude boxes for manually reviewed outliers.",
    )
    args = parser.parse_args()

    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    overrides: dict[str, dict[str, list[list[int]]]] = {}
    if args.overrides:
        overrides = json.loads(args.overrides.read_text(encoding="utf-8"))
    ocr_boxes_by_path: dict[str, list[tuple[int, int, int, int]]] = {}
    if args.ocr_report:
        report = json.loads(args.ocr_report.read_text(encoding="utf-8"))
        for ocr_record in report["records"]:
            boxes = [
                tuple(map(int, box["box"]))
                for box in ocr_record.get("boxes", [])
            ]
            if boxes:
                ocr_boxes_by_path[str(ocr_record["path"])] = boxes
    crop_x, crop_y, crop_width, crop_height = args.source_box
    written: list[str] = []
    for record in batch["records"]:
        relative = Path(record["path"])
        if (
            args.path_contains
            and args.path_contains not in relative.as_posix()
        ):
            continue
        localized = Image.open(
            args.localized_root / relative
        ).convert("RGBA")
        clean = Image.open(args.clean_root / relative).convert("RGBA")
        if localized.size != clean.size:
            raise ValueError(
                f"canvas mismatch for {relative}: "
                f"{localized.size} != {clean.size}"
            )
        crop = localized.crop(
            (
                crop_x,
                crop_y,
                crop_x + crop_width,
                crop_y + crop_height,
            )
        )
        if args.mode == "challenge":
            mask = challenge_text_mask(crop)
        elif args.mode == "green":
            relative_posix = relative.as_posix()
            include_white = (
                "/IZM2/" in relative_posix
                or "/Survival/" in relative_posix
            )
            mask = green_text_mask(
                crop,
                include_white=include_white,
                include_cream=(
                    include_white
                    or "MiniGames_LEVEL_A170" in relative_posix
                ),
            )
        override = overrides.get(relative.as_posix(), {})
        if args.ocr_report:
            boxes = (
                ocr_boxes_by_path.get(relative.as_posix(), [])
                + [
                    tuple(map(int, box))
                    for box in override.get("include_boxes", [])
                ]
            )
            if not boxes:
                raise ValueError(f"OCR found no English text for {relative}")
            allowed = Image.new("L", crop.size, 0)
            draw = ImageDraw.Draw(allowed)
            # Vision's box already includes the outer lettering stroke. Keep
            # only a one-pixel safety margin so the old rectangular edit
            # boundary cannot leak into the transferred text layer.
            padding = 1
            for box_left, box_top, box_width, box_height in boxes:
                left = box_left - crop_x
                top = box_top - crop_y
                right = left + box_width
                bottom = top + box_height
                if (
                    right <= 0
                    or bottom <= 0
                    or left >= crop_width
                    or top >= crop_height
                ):
                    continue
                draw.rectangle(
                    (
                        max(0, left - padding),
                        max(0, top - padding),
                        min(crop_width, right + padding),
                        min(crop_height, bottom + padding),
                    ),
                    fill=255,
                )
            if allowed.getbbox() is None:
                raise ValueError(
                    f"OCR boxes do not intersect source crop for {relative}"
                )
            mask = ImageChops.multiply(mask, allowed)
        exclude_boxes = override.get("exclude_boxes", [])
        if exclude_boxes:
            retained = Image.new("L", crop.size, 255)
            retained_draw = ImageDraw.Draw(retained)
            for (
                box_left,
                box_top,
                box_width,
                box_height,
            ) in exclude_boxes:
                retained_draw.rectangle(
                    (
                        max(0, box_left - crop_x),
                        max(0, box_top - crop_y),
                        min(crop_width, box_left - crop_x + box_width),
                        min(crop_height, box_top - crop_y + box_height),
                    ),
                    fill=0,
                )
            mask = ImageChops.multiply(mask, retained)
        crop.putalpha(mask)
        layer = Image.new("RGBA", clean.size, (0, 0, 0, 0))
        layer.alpha_composite(crop, (crop_x, crop_y))
        result = Image.alpha_composite(clean, layer)
        output = args.output_root / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        result.save(output, optimize=True)
        written.append(relative.as_posix())
    print(
        f"Transferred generated card text: batch={batch['batch_index']} "
        f"files={len(written)} mode={args.mode}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
