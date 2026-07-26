#!/usr/bin/env python3
"""Merge human-curated runtime strings with the validated language catalog."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


CJK_RE = re.compile(
    r"[\u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff01-\uff60]"
)


def load_dictionary(path: Path) -> dict[str, str]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in parsed.items()
    ):
        raise ValueError(f"Expected a string dictionary: {path}")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--curated", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    translations: dict[str, str] = {}
    conflicts: set[str] = set()
    with args.catalog.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            chinese = row["zh"]
            english = row["en"]
            previous = translations.get(chinese)
            if previous is not None and previous != english:
                conflicts.add(chinese)
                translations.pop(chinese, None)
            elif chinese not in conflicts:
                translations[chinese] = english

    curated_count = 0
    curated_values: dict[str, str] = {}
    for path in args.curated:
        for chinese, english in load_dictionary(path).items():
            if not CJK_RE.search(chinese):
                raise ValueError(f"Runtime source key has no CJK text: {chinese!r}")
            if CJK_RE.search(english):
                raise ValueError(f"Runtime translation still has CJK text: {chinese!r}")
            previous = curated_values.get(chinese)
            if previous is not None and previous != english:
                raise ValueError(
                    f"Conflicting runtime translation for {chinese!r}: "
                    f"{previous!r} vs {english!r}"
                )
            curated_values[chinese] = english
            translations[chinese] = english
            curated_count += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(translations, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Built runtime map: entries={len(translations)} "
        f"curated={curated_count} ambiguous_catalog_sources={len(conflicts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
