#!/usr/bin/env python3
"""Build the complete, full-width level-card title manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ADVENTURE_RE = re.compile(
    r"^TowerDefense/Level/Chapter(?P<chapter>\d+)/"
    r"Adventure_LEVEL(?P=chapter)-(?P<level>\d+)\.png$"
)
FULL_TITLE_CROP = [60, 55, 351, 115]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level-manifest", required=True, type=Path)
    parser.add_argument("--gui-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    existing = json.loads(args.level_manifest.read_text(encoding="utf-8"))
    records = [
        record
        for record in existing["records"]
        if record["kind"] == "card"
    ]
    known_paths = {str(record["path"]) for record in records}

    adventure_count = 0
    for image in sorted(args.gui_root.rglob("Adventure_LEVEL*.png")):
        relative = image.relative_to(args.gui_root).as_posix()
        match = ADVENTURE_RE.fullmatch(relative)
        if match is None:
            continue
        chapter = int(match.group("chapter"))
        level = int(match.group("level"))
        if relative in known_paths:
            raise ValueError(f"duplicate level-card path: {relative}")
        title = f"LEVEL {chapter}-{level}"
        records.append(
            {
                "path": relative,
                "kind": "card",
                "title_lines": [title],
                "title": title,
            }
        )
        known_paths.add(relative)
        adventure_count += 1

    records.sort(key=lambda record: str(record["path"]))
    if len(records) != 524 or adventure_count != 130:
        raise ValueError(
            "unexpected complete card counts: "
            f"all={len(records)}, adventure={adventure_count}"
        )

    payload = {
        "records": records,
        "record_count": len(records),
        "counts": {
            "card": len(records),
            "adventure": adventure_count,
            "other": len(records) - adventure_count,
        },
        "card_crop": FULL_TITLE_CROP,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "Built complete level-card manifest: "
        f"cards={len(records)} adventure={adventure_count} "
        f"crop={FULL_TITLE_CROP}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
