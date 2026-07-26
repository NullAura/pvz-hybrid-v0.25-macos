#!/usr/bin/env python3
"""Create exact-string replacement files for a Godot PCK patch."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from audit_localization_parity import verify_tscn_structure
from level_gameplay_fixes import apply_gameplay_fixes, load_gameplay_fixes
from tscn_layout_overrides import (
    apply_layout_overrides,
    load_layout_overrides,
)


CJK_RE = re.compile(r"[\u3400-\u9fff]")
QUOTED_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
TEXT_EXTENSIONS = {".cfg", ".godot", ".json", ".tres", ".tscn"}


def load_dictionary(path: Path) -> dict[str, str]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in parsed.items()
    ):
        raise ValueError(f"Expected a string dictionary: {path}")
    return parsed


def replace_quoted_strings(text: str, translations: dict[str, str]) -> tuple[str, int]:
    replacements = 0

    def decode_literal(raw: str) -> str:
        return json.loads(
            raw.replace("\r", "\\r").replace("\n", "\\n")
        )

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements
        try:
            source = decode_literal(match.group(0))
        except json.JSONDecodeError:
            return match.group(0)
        translated = translations.get(source)
        if translated is None or translated == source:
            return match.group(0)
        replacements += 1
        return json.dumps(translated, ensure_ascii=False)

    return QUOTED_STRING_RE.sub(replace, text), replacements


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--english-translation", type=Path, required=True)
    parser.add_argument("--layout-overrides", type=Path)
    parser.add_argument("--gameplay-fixes", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    translations = load_dictionary(args.translations)
    layout_overrides = load_layout_overrides(args.layout_overrides)
    gameplay_fixes = load_gameplay_fixes(args.gameplay_fixes)
    if args.output.exists():
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True)

    changed_files: list[dict[str, object]] = []
    used: set[str] = set()
    for source_path in args.source.rglob("*"):
        if not source_path.is_file() or source_path.suffix not in TEXT_EXTENSIONS:
            continue
        relative_path = source_path.relative_to(args.source)
        try:
            original = source_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            continue
        patched, count = replace_quoted_strings(original, translations)
        layout_count = 0
        if relative_path.suffix == ".tscn":
            patched, layout_count = apply_layout_overrides(
                patched,
                relative_path.as_posix(),
                layout_overrides,
            )
        gameplay_fix_count = 0
        if relative_path.suffix == ".json":
            patched, gameplay_fix_count = apply_gameplay_fixes(
                patched,
                relative_path.as_posix(),
                gameplay_fixes,
            )
        if relative_path.as_posix() == "project.godot":
            translation_setting = re.compile(
                r'^locale/translations=PackedStringArray\(.*\)$',
                re.MULTILINE,
            )
            forced = translation_setting.sub(
                'locale/fallback="en"\n'
                'locale/translations=PackedStringArray('
                '"res://Asset/Translate/Translate.en.translation")',
                patched,
            )
            if forced != patched:
                patched = forced
                count += 1
        if count == 0 and layout_count == 0 and gameplay_fix_count == 0:
            continue
        if relative_path.suffix == ".tscn":
            verify_tscn_structure(
                original,
                patched,
                translations,
                relative_path.as_posix(),
            )
        for literal in QUOTED_STRING_RE.findall(original):
            try:
                value = json.loads(
                    literal.replace("\r", "\\r").replace("\n", "\\n")
                )
            except json.JSONDecodeError:
                continue
            if value in translations and translations[value] != value:
                used.add(value)
        output_path = args.output / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(patched, encoding="utf-8")
        changed_files.append(
            {
                "path": relative_path.as_posix(),
                "replacements": count,
                "layout_overrides": layout_count,
                "gameplay_fixes": gameplay_fix_count,
            }
        )

    translation_relative_path = Path("Asset/Translate/Translate.en.translation")
    translation_output = args.output / translation_relative_path
    translation_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.english_translation, translation_output)
    changed_files.append(
        {"path": translation_relative_path.as_posix(), "replacements": 1}
    )

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(
            {
                "files": changed_files,
                "replacement_count": sum(
                    int(item["replacements"]) for item in changed_files
                ),
                "used_source_strings": len(used),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Built resource patch: files={len(changed_files)} "
        f"replacements={sum(int(item['replacements']) for item in changed_files)} "
        f"source_strings={len(used)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
