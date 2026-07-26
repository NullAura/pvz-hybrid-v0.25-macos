#!/usr/bin/env python3
"""Paste an image-generated chapter-title sheet into exact cover canvases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sheet", type=Path, required=True)
    parser.add_argument("--gui-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected_size = tuple(manifest["sheet_size"])
    generated = Image.open(args.sheet).convert("RGBA")
    if generated.size != expected_size:
        generated = generated.resize(
            expected_size, Image.Resampling.LANCZOS
        )

    written = 0
    for record in manifest["records"]:
        x, y, width, height = map(int, record["cell"])
        title_crop = generated.crop((x, y, x + width, y + height))
        relative = Path(record["path"])
        source = Image.open(args.gui_root / relative).convert("RGBA")
        if list(source.size) != list(record["canvas"]):
            raise ValueError(
                f"Canvas changed for {relative}: {source.size}"
            )
        source.paste(title_crop, (0, 0))
        destination = args.output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.save(destination, optimize=True)
        written += 1

    print(f"Applied generated chapter sheet: files={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
