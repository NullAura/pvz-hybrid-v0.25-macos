#!/usr/bin/env python3
"""Build image-generation sheets from exact Chinese text regions.

Each generated region is later pasted back into the original texture canvas,
so node geometry and every pixel outside the text crop remain unchanged.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from PIL import Image


GROUP_COLUMNS = {
    "shop-tabs": 4,
    "shop-bottom": 4,
    "shop-misc": 2,
    "editor-small": 4,
    "editor-large": 4,
    "editor-mode": 2,
    "online-buttons": 3,
    "shop-navigation": 4,
    "try-tags": 6,
    "try-almanac": 3,
    "battle-words": 2,
    "standalone-titles": 2,
    "standalone-symbols": 2,
    "chapter-static-title": 1,
}


def group_for(path: str) -> str:
    if path.startswith("AwardSettlement/Paper/"):
        return "doc-" + Path(path).stem.lower()
    if path.startswith("Help/"):
        return "doc-" + Path(path).stem.lower()
    if path == "LevelEditor/GameplayManual.png":
        return "doc-gameplay-manual"
    if path == "OnlineLevelExchange/OnlineLevelExchangeReadPaper.png":
        return "doc-reward-exchange"
    if re.search(r"Shop/Shop_Sort", path):
        return "shop-tabs"
    if re.search(r"Shop/Newbottom_", path):
        return "shop-bottom"
    if path in {
        "Shop/StoreNextButton.png",
        "Shop/StoreNextButtonHighlight.png",
        "Shop/StorePrevButton.png",
        "Shop/StorePrevButtonHighlight.png",
    }:
        return "shop-navigation"
    if path in {
        "Shop/Item/CoinCollect.png",
        "Shop/Item/SunCollect.png",
        "Shop/StoreSign.png",
        "StarExchange/StarExchangeTitle.png",
        "TryLevel/TryLevelTagTitlePlantstry.png",
    }:
        return "shop-misc"
    if re.search(r"LevelEditor/DiySelect_[1-4]", path):
        return "editor-small"
    if path in {
        "LevelEditor/DiySelect_GameplayManual.png",
        "LevelEditor/DiySelect_GameplayManual_highlight.png",
    }:
        return "editor-small"
    if re.search(r"LevelEditor/DiySelect_[5-6]", path):
        return "editor-large"
    if path in {
        "LevelEditor/SurvivalEndlessIcon.png",
        "LevelEditor/SurvivalIcon.png",
    }:
        return "editor-mode"
    if path.startswith("OnlineLevelExchange/"):
        return "online-buttons"
    if re.search(r"TryLevel/TryLevelTag(?:Star|Purple|Rainbow)", path):
        return "try-tags"
    if path.startswith("TryLevel/ShopLevel_Almanac"):
        return "try-almanac"
    if path.startswith("General/BattleWord/"):
        return "battle-words"
    if path == "General/DialogBox/DialogMenu.png":
        return "standalone-titles"
    if path in {
        "General/FlagMeter/FlagMeterLevelProgress.png",
        "General/Special/LuckyBag.png",
    }:
        return "standalone-symbols"
    if path == "TowerDefense/Level/IZM/ChapterIZM.png":
        return "chapter-static-title"
    raise ValueError(f"No graphic crop group for {path}")


def crop_box(record: dict[str, object]) -> tuple[int, int, int, int]:
    path = str(record["path"])
    width = int(record["width"])
    height = int(record["height"])
    boxes = record["boxes"]
    if path.startswith("TryLevel/ShopLevel_Almanac"):
        return (0, 0, width, height)
    if re.search(
        r"TryLevel/TryLevelTag(?:Star|Purple|Rainbow)", path
    ):
        return (0, 0, width, height)
    if path in {
        "OnlineLevelExchange/OnlineLevelExchangeSelectCustom.png",
        "OnlineLevelExchange/OnlineLevelExchangeSelectPlant.png",
    }:
        return (55, 0, width, height)
    if path == "LevelEditor/DiySelect_3.png":
        return (0, 165, width, height)
    manual_crops = {
        "LevelEditor/DiySelect_GameplayManual.png": (124, 8, 213, 40),
        "LevelEditor/DiySelect_GameplayManual_highlight.png": (
            124,
            8,
            213,
            40,
        ),
        "Shop/Newbottom_plants_press.png": (99, 18, 228, 67),
        "Shop/StoreNextButton.png": (8, 0, 116, 36),
        "Shop/StoreNextButtonHighlight.png": (8, 0, 116, 36),
        "Shop/StorePrevButton.png": (7, 0, 96, 34),
        "Shop/StorePrevButtonHighlight.png": (7, 0, 96, 34),
        "General/Special/LuckyBag.png": (24, 25, 68, 62),
        "General/FlagMeter/FlagMeterLevelProgress.png": (
            0,
            0,
            width,
            height,
        ),
        "TowerDefense/Level/IZM/ChapterIZM.png": (
            224,
            268,
            594,
            357,
        ),
    }
    if path in manual_crops:
        return manual_crops[path]

    x0 = min(int(box["box"][0]) for box in boxes)
    y0 = min(int(box["box"][1]) for box in boxes)
    x1 = max(int(box["box"][0]) + int(box["box"][2]) for box in boxes)
    y1 = max(int(box["box"][1]) + int(box["box"][3]) for box in boxes)
    padding_x = max(4, math.ceil((x1 - x0) * 0.08))
    padding_y = max(4, math.ceil((y1 - y0) * 0.12))
    return (
        max(0, x0 - padding_x),
        max(0, y0 - padding_y),
        min(width, x1 + padding_x),
        min(height, y1 + padding_y),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--ocr-boxes", type=Path, required=True)
    parser.add_argument("--gui-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gutter", type=int, default=12)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    box_data = json.loads(args.ocr_boxes.read_text(encoding="utf-8"))
    box_by_path = {
        record["path"]: record for record in box_data["records"]
    }
    grouped: dict[str, list[dict[str, object]]] = {}
    for path, lines in sorted(catalog.items()):
        record = box_by_path.get(path)
        if record is None:
            source = Image.open(args.gui_root / path)
            record = {
                "path": path,
                "width": source.width,
                "height": source.height,
                "boxes": [],
            }
        x0, y0, x1, y1 = crop_box(record)
        grouped.setdefault(group_for(path), []).append(
            {
                "path": path,
                "title_lines": lines,
                "title": " / ".join(lines),
                "crop": [x0, y0, x1 - x0, y1 - y0],
                "canvas": [record["width"], record["height"]],
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    jobs: list[dict[str, object]] = []
    for job_index, (group, records) in enumerate(
        sorted(grouped.items()), start=1
    ):
        columns = min(GROUP_COLUMNS.get(group, 1), len(records))
        rows = math.ceil(len(records) / columns)
        max_width = max(int(record["crop"][2]) for record in records)
        max_height = max(int(record["crop"][3]) for record in records)
        cell_width = max_width + args.gutter * 2
        cell_height = max_height + args.gutter * 2
        sheet = Image.new(
            "RGBA",
            (cell_width * columns, cell_height * rows),
            (255, 0, 255, 255),
        )
        for index, record in enumerate(records):
            x, y, width, height = map(int, record["crop"])
            source = Image.open(
                args.gui_root / str(record["path"])
            ).convert("RGBA")
            crop = source.crop((x, y, x + width, y + height))
            column = index % columns
            row = index // columns
            cell_x = column * cell_width
            cell_y = row * cell_height
            paste_x = cell_x + (cell_width - width) // 2
            paste_y = cell_y + (cell_height - height) // 2
            sheet.alpha_composite(crop, (paste_x, paste_y))
            record["cell"] = [
                paste_x,
                paste_y,
                width,
                height,
            ]

        stem = f"graphic-job-{job_index:02d}-{group}"
        sheet_name = stem + "-original.png"
        manifest_name = stem + ".json"
        sheet.save(args.output_dir / sheet_name, optimize=True)
        payload = {
            "job_index": job_index,
            "group": group,
            "sheet": sheet_name,
            "generated_sheet": stem + "-generated.png",
            "columns": columns,
            "rows": rows,
            "sheet_size": list(sheet.size),
            "records": records,
        }
        (args.output_dir / manifest_name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        jobs.append(
            {
                "job": manifest_name,
                "sheet": sheet_name,
                "group": group,
                "records": len(records),
            }
        )

    index = {
        "jobs": jobs,
        "job_count": len(jobs),
        "record_count": sum(len(records) for records in grouped.values()),
    }
    (args.output_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Built graphic crop jobs: jobs={len(jobs)} "
        f"records={index['record_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
