#!/usr/bin/env python3
"""Build an original-over-localized visual QA sheet for one graphic job."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image


def fitted(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = min(width / image.width, height / image.height)
    size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--localized-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--cell-width", type=int, default=360)
    parser.add_argument("--cell-height", type=int, default=240)
    parser.add_argument("--gutter", type=int, default=12)
    args = parser.parse_args()

    job = json.loads(args.job.read_text(encoding="utf-8"))
    records = job["records"]
    columns = min(args.columns, len(records))
    rows = math.ceil(len(records) / columns)
    pair_height = args.cell_height * 2 + args.gutter
    sheet = Image.new(
        "RGBA",
        (
            columns * args.cell_width
            + (columns + 1) * args.gutter,
            rows * pair_height + (rows + 1) * args.gutter,
        ),
        (255, 0, 255, 255),
    )
    for index, record in enumerate(records):
        relative = Path(record["path"])
        crop_x, crop_y, crop_width, crop_height = map(
            int, record["crop"]
        )
        box = (
            crop_x,
            crop_y,
            crop_x + crop_width,
            crop_y + crop_height,
        )
        original = Image.open(
            args.original_root / relative
        ).convert("RGBA").crop(box)
        localized = Image.open(
            args.localized_root / relative
        ).convert("RGBA").crop(box)
        original = fitted(
            original,
            args.cell_width,
            args.cell_height,
        )
        localized = fitted(
            localized,
            args.cell_width,
            args.cell_height,
        )
        column = index % columns
        row = index // columns
        left = args.gutter + column * (
            args.cell_width + args.gutter
        )
        top = args.gutter + row * (
            pair_height + args.gutter
        )
        for image, y in (
            (original, top),
            (localized, top + args.cell_height + args.gutter),
        ):
            x = left + (args.cell_width - image.width) // 2
            y += (args.cell_height - image.height) // 2
            sheet.alpha_composite(image, (x, y))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, optimize=True)
    print(
        f"Wrote {args.output}: group={job['group']} "
        f"records={len(records)} grid={columns}x{rows}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
