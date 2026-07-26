#!/usr/bin/env python3
"""Build and validate the English catalog from human-curated translations."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


CJK_RE = re.compile(
    r"[\u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff01-\uff60]"
)
PROTECTED_RE = re.compile(
    r"""
    \[[^\]\n]+\]
    |\{[^{}\n]+\}
    |%(?:\d+\$)?[+\-0-9.*]*[sdioxXfcv]
    |https?://[^\s\]]+
    |(?:res|user)://[^\s\]]+
    |(?<!\S)/[a-zA-Z][a-zA-Z0-9_-]*
    """,
    re.VERBOSE,
)


def read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def load_curated(path: Path) -> dict[str, str]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in parsed.items()
    ):
        raise ValueError(f"Curated translations must be a string dictionary: {path}")
    return parsed


def protected_tokens(text: str) -> Counter[str]:
    return Counter(PROTECTED_RE.findall(text))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chinese", type=Path, required=True)
    parser.add_argument("--curated", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--messages-json", type=Path, required=True)
    args = parser.parse_args()

    chinese_rows = read_catalog(args.chinese)
    curated: dict[str, str] = {}
    for path in args.curated:
        for key, value in load_curated(path).items():
            if key in curated:
                raise ValueError(f"Duplicate curated key: {key}")
            curated[key] = value

    catalog_keys = {row["key"] for row in chinese_rows}
    unknown = sorted(curated.keys() - catalog_keys)
    if unknown:
        raise ValueError(f"Curated files contain {len(unknown)} unknown keys: {unknown[:10]}")

    output_rows: list[dict[str, str]] = []
    missing: list[str] = []
    errors: list[str] = []
    for row in chinese_rows:
        key = row["key"]
        source = row["zh"]
        english = curated.get(key, "")
        if not english:
            missing.append(key)
            continue
        if CJK_RE.search(english):
            errors.append(f"{key}: English text still contains CJK characters")
        if protected_tokens(source) != protected_tokens(english):
            errors.append(f"{key}: protected formatting tokens changed")
        output_rows.append({"key": key, "zh": source, "en": english})

    if missing or errors:
        for message in errors[:50]:
            print(message)
        if len(errors) > 50:
            print(f"... {len(errors) - 50} more validation errors")
        print(f"Missing curated translations: {len(missing)}")
        for key in missing[:50]:
            print(key)
        if len(missing) > 50:
            print(f"... {len(missing) - 50} more missing keys")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=["key", "zh", "en"])
        writer.writeheader()
        writer.writerows(output_rows)

    args.messages_json.parent.mkdir(parents=True, exist_ok=True)
    args.messages_json.write_text(
        json.dumps([row["en"] for row in output_rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Validated human-curated catalog: {len(output_rows)} messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
