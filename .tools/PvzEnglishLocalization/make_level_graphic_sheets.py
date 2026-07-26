#!/usr/bin/env python3
"""Create exact-crop contact sheets for image-generated level-card edits."""

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
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--gutter", type=int, default=10)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    crop_x, crop_y, crop_width, crop_height = manifest["card_crop"]
    records = [
        record
        for record in manifest["records"]
        if record["kind"] == "card"
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    batches: list[dict[str, object]] = []
    for batch_index, start in enumerate(
        range(0, len(records), args.batch_size), start=1
    ):
        batch_records = records[start : start + args.batch_size]
        rows = math.ceil(len(batch_records) / args.columns)
        cell_width = crop_width + args.gutter * 2
        cell_height = crop_height + args.gutter * 2
        sheet = Image.new(
            "RGBA",
            (cell_width * args.columns, cell_height * rows),
            (255, 0, 255, 255),
        )
        for index, record in enumerate(batch_records):
            source = Image.open(
                args.gui_root / record["path"]
            ).convert("RGBA")
            if (
                source.width < crop_x + crop_width
                or source.height < crop_y + crop_height
            ):
                raise ValueError(
                    f"Title crop exceeds card canvas for "
                    f"{record['path']}: {source.size}"
                )
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

        stem = f"level-cards-{batch_index:02d}"
        sheet_path = args.output_dir / f"{stem}-original.png"
        batch_path = args.output_dir / f"{stem}.json"
        sheet.save(sheet_path, optimize=True)
        batch_payload = {
            "batch_index": batch_index,
            "sheet": sheet_path.name,
            "generated_sheet": f"{stem}-generated.png",
            "columns": args.columns,
            "rows": rows,
            "records": batch_records,
        }
        batch_path.write_text(
            json.dumps(batch_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        batches.append(
            {
                "batch": batch_path.name,
                "sheet": sheet_path.name,
                "records": len(batch_records),
            }
        )

    index = {
        "batches": batches,
        "batch_count": len(batches),
        "record_count": len(records),
    }
    (args.output_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Created level-card sheets: batches={len(batches)} "
        f"records={len(records)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
