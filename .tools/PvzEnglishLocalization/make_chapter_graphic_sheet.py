#!/usr/bin/env python3
"""Build one exact-top-crop sheet for non-Adventure chapter covers."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--gui-root", type=Path, required=True)
    parser.add_argument("--output-sheet", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--gutter", type=int, default=10)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = [
        record
        for record in manifest["records"]
        if record["kind"] == "chapter"
    ]
    crop_width, crop_height = 720, 160
    cell_width = crop_width + args.gutter * 2
    cell_height = crop_height + args.gutter * 2
    rows = math.ceil(len(records) / args.columns)
    sheet = Image.new(
        "RGBA",
        (cell_width * args.columns, cell_height * rows),
        (255, 0, 255, 255),
    )
    output_records: list[dict[str, object]] = []
    for index, record in enumerate(records):
        original = Image.open(
            args.gui_root / record["path"]
        ).convert("RGBA")
        if original.size != (720, 484):
            raise ValueError(
                f"Unexpected chapter canvas for {record['path']}: "
                f"{original.size}"
            )
        crop = original.crop((0, 0, crop_width, crop_height))
        column = index % args.columns
        row = index // args.columns
        x = column * cell_width + args.gutter
        y = row * cell_height + args.gutter
        sheet.alpha_composite(crop, (x, y))
        output_records.append(
            {
                **record,
                "cell": [x, y, crop_width, crop_height],
                "canvas": list(original.size),
            }
        )

    args.output_sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output_sheet, optimize=True)
    args.output_manifest.write_text(
        json.dumps(
            {
                "sheet": args.output_sheet.name,
                "sheet_size": list(sheet.size),
                "columns": args.columns,
                "rows": rows,
                "records": output_records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Created chapter graphic sheet: records={len(records)} "
        f"grid={args.columns}x{rows} size={sheet.size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
