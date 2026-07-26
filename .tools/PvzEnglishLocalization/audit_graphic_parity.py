#!/usr/bin/env python3
"""Verify localized GUI canvases, edit regions, and interaction states."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from PIL import Image, ImageChops


CARD_CROP = (60, 55, 351, 115)
ADVENTURE_2_5_CROP = (60, 55, 351, 185)
ADVENTURE_CARD_RE = re.compile(
    r"^TowerDefense/Level/Chapter\d+/Adventure_LEVEL\d+-\d+\.png$"
)

INTERACTION_STATE_PAIRS = [
    ("LevelEditor/DiySelect_1.png", "LevelEditor/DiySelect_1_highlight.png"),
    ("LevelEditor/DiySelect_2.png", "LevelEditor/DiySelect_2_highlight.png"),
    ("LevelEditor/DiySelect_3.png", "LevelEditor/DiySelect_3_highlight.png"),
    ("LevelEditor/DiySelect_4.png", "LevelEditor/DiySelect_4_highlight.png"),
    ("LevelEditor/DiySelect_5.png", "LevelEditor/DiySelect_5_highlight.png"),
    ("LevelEditor/DiySelect_6.png", "LevelEditor/DiySelect_6_highlight.png"),
    (
        "LevelEditor/DiySelect_GameplayManual.png",
        "LevelEditor/DiySelect_GameplayManual_highlight.png",
    ),
    (
        "OnlineLevelExchange/OnlineLevelExchangeEnter.png",
        "OnlineLevelExchange/OnlineLevelExchangeEnterHover.png",
    ),
    (
        "OnlineLevelExchange/OnlineLevelExchangeRead.png",
        "OnlineLevelExchange/OnlineLevelExchangeReadHover.png",
    ),
    ("Shop/Newbottom_bag.png", "Shop/Newbottom_bag_press.png"),
    ("Shop/Newbottom_plants.png", "Shop/Newbottom_plants_press.png"),
    ("Shop/Newbottom_shop.png", "Shop/Newbottom_shop_press.png"),
    ("Shop/Newbottom_star.png", "Shop/Newbottom_star_press.png"),
    ("Shop/Shop_Sort0.png", "Shop/Shop_Sort0_select.png"),
    ("Shop/Shop_Sort1.png", "Shop/Shop_Sort1_select.png"),
    ("Shop/Shop_Sort2.png", "Shop/Shop_Sort2_select.png"),
    ("Shop/Shop_Sort3.png", "Shop/Shop_Sort3_select.png"),
    ("Shop/Shop_Sort4.png", "Shop/Shop_Sort4_select.png"),
    ("Shop/StoreNextButton.png", "Shop/StoreNextButtonHighlight.png"),
    ("Shop/StorePrevButton.png", "Shop/StorePrevButtonHighlight.png"),
    ("TryLevel/ShopLevel_Almanac.png", "TryLevel/ShopLevel_Almanac_press.png"),
    (
        "TryLevel/TryLevelTagPurple.png",
        "TryLevel/TryLevelTagPurpleUnselected.png",
    ),
    (
        "TryLevel/TryLevelTagRainbow.png",
        "TryLevel/TryLevelTagRainbowUnselected.png",
    ),
    (
        "TryLevel/TryLevelTagStar.png",
        "TryLevel/TryLevelTagStarUnselected.png",
    ),
]

MAIN_MENU_STATE_PAIRS = [
    ("MainMenu/AdventureMode0.png", "MainMenu/AdventureMode1.png"),
    ("MainMenu/BattleGame.png", "MainMenu/BattleGameLight.png"),
    ("MainMenu/ChallengeMode0.png", "MainMenu/ChallengeMode1.png"),
    ("MainMenu/IZM2Game.png", "MainMenu/IZM2GameLight.png"),
    ("MainMenu/MiniGame.png", "MainMenu/MiniGame_light.png"),
    ("MainMenu/MoreGames.png", "MainMenu/MoreGamesLight.png"),
    ("MainMenu/PuzzleGame.png", "MainMenu/PuzzleGameLight.png"),
    (
        "MainMenu/SelectorScreenAlmanac.png",
        "MainMenu/SelectorScreenAlmanacHighlight.png",
    ),
    (
        "MainMenu/SelectorScreenDiyButton.png",
        "MainMenu/SelectorScreenDiyButtonPress.png",
    ),
    ("MainMenu/SelectorScreenHelp1.png", "MainMenu/SelectorScreenHelp2.png"),
    (
        "MainMenu/SelectorScreenOptions1.png",
        "MainMenu/SelectorScreenOptions2.png",
    ),
    ("MainMenu/SelectorScreenQuit1.png", "MainMenu/SelectorScreenQuit2.png"),
    (
        "MainMenu/SelectorScreenStore.png",
        "MainMenu/SelectorScreenStoreHighlight.png",
    ),
    (
        "MainMenu/StarsExchangeButton.png",
        "MainMenu/StarsExchangeButtonLight.png",
    ),
    ("MainMenu/SurvivalMode0.png", "MainMenu/SurvivalMode1.png"),
    (
        "MainMenu/SelectorScreenWoodSign2.png",
        "MainMenu/SelectorScreenWoodSign2Press.png",
    ),
    (
        "MainMenu/SelectorScreenWoodSign5.png",
        "MainMenu/SelectorScreenWoodSign5Press.png",
    ),
]


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def difference_mask(left: Image.Image, right: Image.Image) -> Image.Image:
    difference = ImageChops.difference(
        left.convert("RGBA"), right.convert("RGBA")
    )
    mask = Image.new("L", difference.size, 0)
    for band in difference.split():
        mask = ImageChops.lighter(mask, band)
    return mask


def load_crop_jobs(directory: Path) -> dict[str, tuple[int, int, int, int]]:
    crops: dict[str, tuple[int, int, int, int]] = {}
    for manifest_path in sorted(directory.glob("graphic-job-*.json")):
        manifest = read_json(manifest_path)
        for record in manifest["records"]:
            path = str(record["path"])
            crop = tuple(map(int, record["crop"]))
            if path in crops:
                raise ValueError(f"duplicate graphic crop path: {path}")
            crops[path] = crop
    return crops


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", required=True, type=Path)
    parser.add_argument("--localized-root", required=True, type=Path)
    parser.add_argument("--crop-jobs", required=True, type=Path)
    parser.add_argument("--level-manifest", required=True, type=Path)
    parser.add_argument("--expected-files", type=int, default=671)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    localized_paths = {
        path.relative_to(args.localized_root).as_posix(): path
        for path in args.localized_root.rglob("*.png")
    }
    if len(localized_paths) != args.expected_files:
        raise ValueError(
            f"expected {args.expected_files} localized PNGs, "
            f"found {len(localized_paths)}"
        )

    crop_by_path = load_crop_jobs(args.crop_jobs)
    level_manifest = read_json(args.level_manifest)
    for record in level_manifest["records"]:
        if record["kind"] == "card":
            crop_by_path[str(record["path"])] = CARD_CROP
    for path in localized_paths:
        if ADVENTURE_CARD_RE.fullmatch(path):
            crop_by_path[path] = CARD_CROP
    crop_by_path[
        "TowerDefense/Level/Chapter2/Adventure_LEVEL2-5.png"
    ] = ADVENTURE_2_5_CROP

    chapter_paths = {
        path
        for path in localized_paths
        if path.startswith("TowerDefense/Level/")
        and path not in crop_by_path
    }
    for path in chapter_paths:
        crop_by_path[path] = (0, 0, 720, 160)

    full_canvas_paths = {
        path for path in localized_paths if path.startswith("MainMenu/")
    }
    assigned_paths = set(crop_by_path) | full_canvas_paths
    if assigned_paths != set(localized_paths):
        raise ValueError(
            "graphic crop coverage mismatch: "
            f"unassigned={sorted(set(localized_paths) - assigned_paths)} "
            f"unknown={sorted(assigned_paths - set(localized_paths))}"
        )

    outside_crop_verified = 0
    full_canvas_verified = 0
    changed_files = 0
    errors: list[str] = []
    for relative, localized_path in sorted(localized_paths.items()):
        original_path = args.original_root / relative
        if not original_path.is_file():
            errors.append(f"missing original image: {relative}")
            continue
        original = Image.open(original_path).convert("RGBA")
        localized = Image.open(localized_path).convert("RGBA")
        if original.size != localized.size:
            errors.append(
                f"canvas changed for {relative}: "
                f"{original.size} -> {localized.size}"
            )
            continue
        mask = difference_mask(original, localized)
        if mask.getbbox() is None:
            errors.append(f"localized image did not change: {relative}")
            continue
        changed_files += 1

        crop = crop_by_path.get(relative)
        if crop is None:
            full_canvas_verified += 1
            continue
        x, y, width, height = crop
        if (
            x < 0
            or y < 0
            or width <= 0
            or height <= 0
            or x + width > original.width
            or y + height > original.height
        ):
            errors.append(f"invalid crop for {relative}: {crop}")
            continue
        outside = mask.copy()
        outside.paste(0, (x, y, x + width, y + height))
        if outside.getbbox() is not None:
            errors.append(f"pixels changed outside the text crop: {relative}")
            continue
        outside_crop_verified += 1

    state_pairs = INTERACTION_STATE_PAIRS + MAIN_MENU_STATE_PAIRS
    distinct_state_pairs = 0
    for first, second in state_pairs:
        first_path = localized_paths.get(first)
        second_path = localized_paths.get(second)
        if first_path is None or second_path is None:
            errors.append(f"missing interaction-state pair: {first} / {second}")
            continue
        first_image = Image.open(first_path).convert("RGBA")
        second_image = Image.open(second_path).convert("RGBA")
        if (
            first_image.size == second_image.size
            and difference_mask(first_image, second_image).getbbox() is None
        ):
            errors.append(
                f"interaction states became identical: {first} / {second}"
            )
            continue
        distinct_state_pairs += 1

    result = {
        "localized_pngs": len(localized_paths),
        "changed_pngs": changed_files,
        "exact_canvas_pngs": len(localized_paths) - sum(
            error.startswith("canvas changed") for error in errors
        ),
        "outside_crop_verified": outside_crop_verified,
        "full_canvas_verified": full_canvas_verified,
        "chapter_covers": len(chapter_paths),
        "interaction_state_pairs": len(state_pairs),
        "distinct_state_pairs": distinct_state_pairs,
        "status": "passed" if not errors else "failed",
        "errors": errors,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
