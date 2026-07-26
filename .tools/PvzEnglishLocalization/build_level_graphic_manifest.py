#!/usr/bin/env python3
"""Map localized level-card text to the exact GUI textures that display it.

The mapping is derived from LevelResource UIDs and the already human-curated
English level catalog. No machine translation is performed here.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
UID_RE = re.compile(r'uid="([^"]+)"')
SOURCE_RE = re.compile(
    r'^source_file="res://Asset/Texture/GUI/(.+\.png)"', re.MULTILINE
)

CHAPTER_TITLES = {
    "TowerDefense/Level/Challenge/Diamond/ChapterDiamond.png": [
        "PREMIUM DIAMOND CARDS"
    ],
    "TowerDefense/Level/Challenge/Gold/ChapterGold.png": [
        "ULTIMATE GOLD CARDS"
    ],
    "TowerDefense/Level/Survival/Classic/SurvivalClassic.png": [
        "CLASSIC MODES"
    ],
    "TowerDefense/Level/Survival/Entertainment/SurvivalEntertainment.png": [
        "PARTY MODES"
    ],
    "TowerDefense/Level/MiniGames/ChapterMiniGames.png": [
        "CLASSIC MINI-GAMES"
    ],
    "TowerDefense/Level/Vase/ChapterVase.png": ["VASEBREAKER"],
    "TowerDefense/Level/IZM/ChapterIZM.png": ["I, ZOMBIE"],
    "TowerDefense/Level/IZM2/IZM2Chapter1.png": [
        "FRONT YARD TRIALS"
    ],
    "TowerDefense/Level/IZM2/IZM2Chapter2.png": [
        "ZOMBIE GRAVEYARD"
    ],
    "TowerDefense/Level/IZM2/IZM2Chapter2Lock.png": [
        "ZOMBIE GRAVEYARD"
    ],
    "TowerDefense/Level/IZM2/IZM2Chapter3.png": ["POOL BREAKOUT"],
    "TowerDefense/Level/IZM2/IZM2Chapter3Lock.png": [
        "POOL BREAKOUT"
    ],
    "TowerDefense/Level/Shooting/ChapterShooting.png": ["SHOOTING MODE"],
}


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def texture_uid_map(gui_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for import_file in gui_root.rglob("*.png.import"):
        text = import_file.read_text(encoding="utf-8", errors="ignore")
        uid_match = UID_RE.search(text)
        source_match = SOURCE_RE.search(text)
        if uid_match and source_match:
            result[uid_match.group(1)] = source_match.group(1)
    return result


def config_uid_map(config_root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for resource in config_root.rglob("*.tres"):
        first_line = resource.open(
            "r", encoding="utf-8", errors="ignore"
        ).readline()
        match = UID_RE.search(first_line)
        if match:
            result[match.group(1)] = resource
    return result


def config_level_name(resource: Path | None) -> str | None:
    if resource is None:
        return None
    json_path = resource.with_suffix(".json")
    if json_path.is_file():
        text = json_path.read_text(encoding="utf-8", errors="ignore")
        try:
            value = json.loads(text).get("LevelName")
            if isinstance(value, str):
                return value
        except json.JSONDecodeError:
            match = re.search(r'"LevelName"\s*:\s*"([^"]+)"', text)
            if match:
                return match.group(1)
    text = resource.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r'^levelName = "([^"]*)"', text, re.MULTILINE)
    return match.group(1) if match else None


def challenge_title(
    save_key: str, ui_catalog: dict[str, str]
) -> list[str]:
    diamond = re.fullmatch(
        r"Challenge_Level_Diamond(\d+)_(\d+)", save_key
    )
    gold = re.fullmatch(r"Challenge_Level(\d+)_(\d+)", save_key)
    if diamond:
        group, number = map(int, diamond.groups())
        catalog_key = f"CHALLENGE_LEVEL_DIALMONDNAME_{group}"
    elif gold:
        group, number = map(int, gold.groups())
        catalog_key = f"CHALLENGE_LEVEL_NAME_{group}"
    else:
        raise ValueError(f"Unrecognized challenge save key: {save_key}")
    translated = ui_catalog[catalog_key].replace(
        "{LevelNumber}", str(number)
    )
    suffix = f" Challenge - {number}"
    if not translated.endswith(suffix):
        raise ValueError(
            f"Unexpected challenge title for {save_key}: {translated}"
        )
    return [translated[: -len(suffix)], f"CHALLENGE {number}"]


def ordinary_title(
    mode: str,
    chapter_index: int,
    level_index: int,
    save_key: str,
    level_name: str | None,
) -> list[str]:
    if mode == "IZM2":
        return [
            f"LEVEL {chapter_index}-{level_index}",
            "I, ZOMBIE",
        ]
    if level_name is None:
        raise ValueError(f"Missing English level name for {save_key}")
    match = re.search(r"_(\d+)$", save_key)
    number = int(match.group(1)) if match else level_index
    title = level_name.replace("{LevelNumber}", str(number))
    survival = re.fullmatch(r"(.+)\s+\((Basic|Advanced|Endless)\)", title)
    if survival:
        return [survival.group(1), survival.group(2).upper()]
    numbered = re.fullmatch(r"(.+)\s+-\s+(\d+)", title)
    if numbered:
        return [f"{numbered.group(1)} {numbered.group(2)}"]
    return [title]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level-resource", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--gui-root", type=Path, required=True)
    parser.add_argument("--localized-root", type=Path, required=True)
    parser.add_argument("--ocr-report", type=Path, required=True)
    parser.add_argument("--ui-catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    level_resource = read_json(args.level_resource)
    if not isinstance(level_resource, dict):
        raise TypeError("LevelResource root must be an object")
    ui_catalog = read_json(args.ui_catalog)
    if not isinstance(ui_catalog, dict):
        raise TypeError("UI catalog root must be an object")

    image_by_uid = texture_uid_map(args.gui_root)
    config_by_uid = config_uid_map(args.config_root)
    active: dict[str, dict[str, object]] = {}
    for mode, mode_data in level_resource.items():
        for chapter_index, chapter in enumerate(
            mode_data["Chapter"], start=1
        ):
            for level_index, level in enumerate(
                chapter["Level"], start=1
            ):
                relative = image_by_uid.get(level["UnlockImage"])
                if relative is None:
                    continue
                config = config_by_uid.get(level["Level"]["Normal"])
                active[relative] = {
                    "mode": mode,
                    "chapter_index": chapter_index,
                    "level_index": level_index,
                    "save_key": level["SaveKey"],
                    "level_name": config_level_name(config),
                }

    candidates: set[str] = {
        relative
        for relative, item in active.items()
        if item["mode"] != "Adventure"
        and not (args.localized_root / relative).is_file()
    }
    for line in args.ocr_report.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        relative = line.split("\t", 1)[0]
        if not relative.startswith("TowerDefense/Level/"):
            continue
        if (args.localized_root / relative).is_file():
            continue
        candidates.add(relative)

    records: list[dict[str, object]] = []
    for relative in sorted(candidates):
        source = args.gui_root / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        if relative in CHAPTER_TITLES:
            title_lines = CHAPTER_TITLES[relative]
            kind = "chapter"
        else:
            item = active.get(relative)
            if item is None:
                slot = re.fullmatch(
                    r"TowerDefense/Level/MiniGames/"
                    r"MiniGames_LEVEL_A03(\d\d)\.png",
                    relative,
                )
                if not slot:
                    raise ValueError(
                        f"No active level mapping for {relative}"
                    )
                title_lines = [f"SLOT MACHINE {int(slot.group(1))}"]
            elif item["mode"] == "Challenge":
                title_lines = challenge_title(
                    str(item["save_key"]), ui_catalog
                )
            else:
                title_lines = ordinary_title(
                    str(item["mode"]),
                    int(item["chapter_index"]),
                    int(item["level_index"]),
                    str(item["save_key"]),
                    (
                        str(item["level_name"])
                        if item["level_name"] is not None
                        else None
                    ),
                )
            kind = "card"

        if any(CJK_RE.search(line) for line in title_lines):
            raise ValueError(
                f"CJK remained in English title for {relative}: "
                f"{title_lines}"
            )
        records.append(
            {
                "path": relative,
                "kind": kind,
                "title_lines": title_lines,
                "title": " / ".join(title_lines),
            }
        )

    records.sort(key=lambda item: str(item["path"]))
    counts = {
        kind: sum(item["kind"] == kind for item in records)
        for kind in ("card", "chapter")
    }
    if counts != {"card": 394, "chapter": 13}:
        raise ValueError(f"Unexpected manifest counts: {counts}")
    payload = {
        "records": records,
        "record_count": len(records),
        "counts": counts,
        "card_crop": [180, 40, 210, 110],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Built level graphic manifest: records={len(records)} "
        f"cards={counts['card']} chapters={counts['chapter']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
