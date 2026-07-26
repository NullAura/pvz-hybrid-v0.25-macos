#!/usr/bin/env python3
"""Apply reviewed, declarative fixes to known-bad upstream level values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_gameplay_fixes(path: Path | None) -> dict[str, list[dict[str, Any]]]:
    if path is None:
        return {}
    parsed = json.loads(path.read_text(encoding="utf-8"))
    fixes = parsed.get("fixes")
    if not isinstance(fixes, list):
        raise ValueError(f"gameplay fix file has no fixes array: {path}")
    result: dict[str, list[dict[str, Any]]] = {}
    for fix in fixes:
        resource_path = str(fix["path"]).removeprefix("res://").lstrip("/")
        operations = fix.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ValueError(f"gameplay fix has no operations: {resource_path}")
        result.setdefault(resource_path, []).extend(operations)
    return result


def apply_gameplay_fixes(
    text: str,
    resource_path: str,
    fixes: dict[str, list[dict[str, Any]]],
) -> tuple[str, int]:
    operations = fixes.get(resource_path, [])
    if not operations:
        return text, 0
    document = json.loads(text)
    for operation in operations:
        keys = operation.get("keys")
        if not isinstance(keys, list) or not keys:
            raise ValueError(f"{resource_path}: fix operation has no keys")
        parent = document
        for key in keys[:-1]:
            parent = parent[key]
        final_key = keys[-1]
        actual = parent[final_key]
        expected = operation.get("before")
        if actual != expected:
            dotted = ".".join(str(key) for key in keys)
            raise ValueError(
                f"{resource_path}.{dotted}: expected {expected!r}, "
                f"found {actual!r}"
            )
        parent[final_key] = operation.get("after")
    return (
        json.dumps(document, ensure_ascii=False, indent="\t") + "\n",
        len(operations),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Read missing patch files from this root before writing them to --root.",
    )
    parser.add_argument("--fixes", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    fixes = load_gameplay_fixes(args.fixes)
    patched: list[dict[str, Any]] = []
    for resource_path in sorted(fixes):
        path = args.root / resource_path
        source_path = path
        if not source_path.is_file() and args.source_root:
            source_path = args.source_root / resource_path
        if not source_path.is_file():
            raise FileNotFoundError(
                f"gameplay fix source is missing: {source_path}"
            )
        original = source_path.read_text(encoding="utf-8-sig")
        updated, count = apply_gameplay_fixes(
            original,
            resource_path,
            fixes,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
        patched.append({"path": resource_path, "operations": count})
    report = {
        "patched": patched,
        "operation_count": sum(item["operations"] for item in patched),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
