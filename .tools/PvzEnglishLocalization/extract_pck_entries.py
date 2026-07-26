#!/usr/bin/env python3
"""Extract selected Godot PCK entries without duplicating unrelated payloads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_localization_parity import read_pack, read_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pck", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--suffix",
        action="append",
        default=[],
        help="Extract only paths ending in this suffix; may be repeated.",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Extract this exact PCK path; may be repeated.",
    )
    parser.add_argument(
        "--path-manifest",
        type=Path,
        help=(
            "Extract paths listed by a JSON manifest's `files` array. "
            "Entries may be path strings or objects containing `path`."
        ),
    )
    parser.add_argument(
        "--path-manifest-suffix",
        action="append",
        default=[],
        help="Keep only manifest paths ending in this suffix; may be repeated.",
    )
    args = parser.parse_args()

    pack = read_pack(args.pck)
    suffixes = tuple(args.suffix)
    paths = {value.removeprefix("res://").lstrip("/") for value in args.path}
    if args.path_manifest:
        manifest = json.loads(args.path_manifest.read_text(encoding="utf-8"))
        manifest_suffixes = tuple(args.path_manifest_suffix)
        for item in manifest["files"]:
            value = item if isinstance(item, str) else item["path"]
            if manifest_suffixes and not value.endswith(manifest_suffixes):
                continue
            paths.add(value.removeprefix("res://").lstrip("/"))
    selected = [
        entry
        for entry in pack.entries.values()
        if (
            (not suffixes and not paths)
            or entry.path in paths
            or (suffixes and entry.path.endswith(suffixes))
        )
    ]
    for entry in selected:
        destination = args.output / entry.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(read_payload(pack, entry))
    print(
        f"Extracted PCK entries: selected={len(selected)} "
        f"total={len(pack.entries)} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
