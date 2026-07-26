#!/usr/bin/env python3
"""Add reviewed English texture payloads to a resource patch.

The original ``.import`` descriptors remain untouched so their UIDs, platform
variants, and runtime references stay byte-identical to the Chinese build.
Only generated ``.ctex`` payloads that already exist in the desktop PCK are
eligible for replacement.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from audit_localization_parity import read_pack


ALLOWED_SUFFIXES = {".ctex"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patch-root", type=Path, required=True)
    parser.add_argument("--localized-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--pck",
        type=Path,
        help="Copy only paths that already exist in this desktop PCK.",
    )
    args = parser.parse_args()

    allowed_paths: set[str] | None = None
    if args.pck:
        allowed_paths = set(read_pack(args.pck).entries)

    copied: list[dict[str, object]] = []
    for source in sorted(args.localized_root.rglob("*")):
        if not source.is_file() or source.suffix not in ALLOWED_SUFFIXES:
            continue
        relative = source.relative_to(args.localized_root)
        if allowed_paths is not None and relative.as_posix() not in allowed_paths:
            continue
        destination = args.patch_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(
            {
                "path": relative.as_posix(),
                "bytes": source.stat().st_size,
            }
        )

    if not copied:
        raise ValueError(f"No imported textures found in {args.localized_root}")

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(
            {
                "files": copied,
                "patched": copied,
                "file_count": len(copied),
                "total_bytes": sum(int(item["bytes"]) for item in copied),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Applied reviewed graphic localization: files={len(copied)} "
        f"bytes={sum(int(item['bytes']) for item in copied)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
