#!/usr/bin/env python3
"""Restore only generated magenta spill from exact original card pixels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def is_magenta_spill(red: int, green: int, blue: int) -> bool:
    """Return whether a pixel belongs to the generated magenta-key family."""
    magenta_strength = min(red, blue) - green
    balanced_endpoints = abs(red - blue) <= 82
    return (
        min(red, blue) >= 36
        and balanced_endpoints
        and magenta_strength >= 30
        and green * 100 <= min(red, blue) * 68
    )


def sanitize_card(generated: Image.Image, original: Image.Image) -> tuple[Image.Image, int]:
    if generated.size != original.size:
        raise ValueError(
            f"canvas mismatch: generated={generated.size} original={original.size}"
        )
    generated_rgba = generated.convert("RGBA")
    original_rgba = original.convert("RGBA")
    output: list[tuple[int, int, int, int]] = []
    restored = 0
    for generated_pixel, original_pixel in zip(
        generated_rgba.get_flattened_data(),
        original_rgba.get_flattened_data(),
        strict=True,
    ):
        red, green, blue, alpha = generated_pixel
        original_red, original_green, original_blue, _ = original_pixel
        generated_is_spill = is_magenta_spill(red, green, blue)
        original_is_magenta = is_magenta_spill(
            original_red,
            original_green,
            original_blue,
        )
        if generated_is_spill and not original_is_magenta:
            output.append(original_pixel)
            restored += 1
        elif alpha == 0:
            # Invisible RGB still bleeds during filtering/import. Canonicalize
            # it instead of carrying hidden magenta into Godot.
            output.append((0, 0, 0, 0))
        else:
            output.append(generated_pixel)
    result = Image.new("RGBA", generated_rgba.size)
    result.putdata(output)
    return result, restored


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--generated-root", type=Path, required=True)
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--path-contains",
        help="Process only records whose relative path contains this text.",
    )
    args = parser.parse_args()

    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    total_restored = 0
    written = 0
    for record in batch["records"]:
        relative = Path(record["path"])
        if (
            args.path_contains
            and args.path_contains not in relative.as_posix()
        ):
            continue
        generated_path = args.generated_root / relative
        original_path = args.original_root / relative
        sanitized, restored = sanitize_card(
            Image.open(generated_path),
            Image.open(original_path),
        )
        output_path = args.output_root / relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sanitized.save(output_path, optimize=True)
        total_restored += restored
        written += 1
    print(
        f"Sanitized generated card chroma spill: "
        f"batch={batch['batch_index']} files={written} "
        f"restored_pixels={total_restored}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
