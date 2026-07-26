#!/usr/bin/env python3
"""Paste one generated graphic-text job into exact original canvases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from apply_generated_level_sheet import alpha_grid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--sheet", type=Path, required=True)
    parser.add_argument("--gui-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--alpha-threshold", type=int, default=32)
    args = parser.parse_args()

    job = json.loads(args.job.read_text(encoding="utf-8"))
    generated = Image.open(args.sheet).convert("RGBA")
    columns = int(job["columns"])
    rows = int(job["rows"])
    x_segments, y_segments = alpha_grid(
        generated,
        columns,
        rows,
        args.alpha_threshold,
    )

    written: list[str] = []
    generated_by_identical_source: dict[
        tuple[bytes, tuple[int, int, int, int], tuple[str, ...]],
        Image.Image,
    ] = {}
    for index, record in enumerate(job["records"]):
        column = index % columns
        row = index // columns
        cell_x0, cell_x1 = x_segments[column]
        cell_y0, cell_y1 = y_segments[row]
        generated_crop = generated.crop(
            (cell_x0, cell_y0, cell_x1, cell_y1)
        )
        alpha = generated_crop.getchannel("A")
        visible_mask = alpha.point(
            lambda value: 255
            if value >= args.alpha_threshold
            else 0
        )
        visible_bbox = visible_mask.getbbox()
        if visible_bbox is None:
            raise ValueError(
                f"Generated cell has no visible pixels: "
                f"group={job['group']} index={index}"
            )
        generated_crop = generated_crop.crop(visible_bbox)
        relative = Path(record["path"])
        source = Image.open(args.gui_root / relative).convert("RGBA")
        if list(source.size) != list(record["canvas"]):
            raise ValueError(
                f"Canvas changed for {relative}: {source.size}, "
                f"expected {record['canvas']}"
            )
        crop_x, crop_y, crop_width, crop_height = map(
            int, record["crop"]
        )
        if generated_crop.size != (crop_width, crop_height):
            generated_crop = generated_crop.resize(
                (crop_width, crop_height), Image.Resampling.LANCZOS
            )
        visible_source = Image.alpha_composite(
            Image.new("RGBA", source.size, (0, 0, 0, 0)),
            source,
        )
        identity_key = (
            hashlib.sha256(visible_source.tobytes()).digest(),
            (crop_x, crop_y, crop_width, crop_height),
            tuple(record["title_lines"]),
        )
        if identity_key in generated_by_identical_source:
            generated_crop = generated_by_identical_source[
                identity_key
            ].copy()
        else:
            generated_by_identical_source[identity_key] = (
                generated_crop.copy()
            )
        source.paste(generated_crop, (crop_x, crop_y))
        destination = args.output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.save(destination, optimize=True)
        written.append(relative.as_posix())

    print(
        f"Applied generated graphic job: group={job['group']} "
        f"files={len(written)} grid={columns}x{rows} "
        f"x_segments={x_segments} y_segments={y_segments}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
