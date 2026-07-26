#!/usr/bin/env python3
"""Create a compact review sheet for one localized level-card batch."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image


def parse_box(value: str) -> tuple[int, int, int, int]:
    parts = tuple(int(part) for part in value.split(","))
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise argparse.ArgumentTypeError("box must be x,y,width,height")
    return parts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--gui-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--box", type=parse_box, default=parse_box("60,55,351,115"))
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--gutter", type=int, default=10)
    args = parser.parse_args()

    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    records = batch["records"]
    crop_x, crop_y, crop_width, crop_height = args.box
    rows = math.ceil(len(records) / args.columns)
    cell_width = crop_width + args.gutter * 2
    cell_height = crop_height + args.gutter * 2
    sheet = Image.new(
        "RGBA",
        (cell_width * args.columns, cell_height * rows),
        (255, 0, 255, 255),
    )
    for index, record in enumerate(records):
        source = Image.open(args.gui_root / record["path"]).convert("RGBA")
        crop = source.crop(
            (
                crop_x,
                crop_y,
                crop_x + crop_width,
                crop_y + crop_height,
            )
        )
        column = index % args.columns
        row = index // args.columns
        sheet.alpha_composite(
            crop,
            (
                column * cell_width + args.gutter,
                row * cell_height + args.gutter,
            ),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, optimize=True)
    print(
        f"Wrote {args.output}: records={len(records)} "
        f"grid={args.columns}x{rows}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
