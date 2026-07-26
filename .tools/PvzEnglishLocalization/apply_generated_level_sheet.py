#!/usr/bin/env python3
"""Split an image-generated level-title sheet and patch exact source canvases."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def segments(values: list[int], threshold: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        active = value > threshold
        if active and start is None:
            start = index
        elif not active and start is not None:
            result.append((start, index))
            start = None
    if start is not None:
        result.append((start, len(values)))
    return result


def merge_to_count(
    source: list[tuple[int, int]], expected: int
) -> list[tuple[int, int]]:
    """Merge the nearest fragments until one segment remains per grid cell."""
    result = list(source)
    while len(result) > expected:
        merge_index = min(
            range(len(result) - 1),
            key=lambda index: (
                result[index + 1][0] - result[index][1]
            ),
        )
        merged = (
            result[merge_index][0],
            result[merge_index + 1][1],
        )
        result[merge_index : merge_index + 2] = [merged]
    return result


def alpha_grid(
    image: Image.Image, columns: int, rows: int, alpha_threshold: int
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    width, height = alpha.size
    pixels = alpha.load()
    x_counts = [
        sum(1 for y in range(height) if pixels[x, y] >= alpha_threshold)
        for x in range(width)
    ]
    y_counts = [
        sum(1 for x in range(width) if pixels[x, y] >= alpha_threshold)
        for y in range(height)
    ]
    x_segments = segments(x_counts, max(1, round(height * 0.01)))
    y_segments = segments(y_counts, max(1, round(width * 0.01)))
    # Chroma-key despill can leave one- or two-pixel alpha fragments along the
    # outer canvas edge. They cannot be real sheet cells, so discard only
    # fragments far smaller than an expected grid cell before validating.
    min_x_span = max(3, round(width / columns * 0.05))
    min_y_span = max(3, round(height / rows * 0.05))
    x_segments = [
        segment
        for segment in x_segments
        if segment[1] - segment[0] >= min_x_span
    ]
    y_segments = [
        segment
        for segment in y_segments
        if segment[1] - segment[0] >= min_y_span
    ]
    x_segments = merge_to_count(x_segments, columns)
    y_segments = merge_to_count(y_segments, rows)
    if len(x_segments) == columns and len(y_segments) == rows:
        return x_segments, y_segments

    # Image-generation edits are sometimes returned as fully opaque RGB
    # images with black letterboxing. In that case, recover the cell grid
    # from the magenta gutters instead of relying on transparency.
    rgb_pixels = rgba.load()

    def is_chroma_key(red: int, green: int, blue: int) -> bool:
        return (
            red >= 180
            and blue >= 150
            and green <= 110
            and red - green >= 90
            and blue - green >= 70
        )

    key_points = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if is_chroma_key(*rgb_pixels[x, y][:3])
    ]
    if not key_points:
        raise ValueError(
            "Could not detect the expected sheet grid from alpha or "
            f"magenta gutters: expected={columns}x{rows}"
        )
    left = min(point[0] for point in key_points)
    top = min(point[1] for point in key_points)
    right = max(point[0] for point in key_points) + 1
    bottom = max(point[1] for point in key_points) + 1
    keyed_width = right - left
    keyed_height = bottom - top
    non_key_x_counts = [
        sum(
            1
            for y in range(top, bottom)
            if not is_chroma_key(*rgb_pixels[x, y][:3])
        )
        for x in range(left, right)
    ]
    non_key_y_counts = [
        sum(
            1
            for x in range(left, right)
            if not is_chroma_key(*rgb_pixels[x, y][:3])
        )
        for y in range(top, bottom)
    ]
    x_segments = [
        (start + left, end + left)
        for start, end in segments(
            non_key_x_counts, max(1, round(keyed_height * 0.01))
        )
    ]
    y_segments = [
        (start + top, end + top)
        for start, end in segments(
            non_key_y_counts, max(1, round(keyed_width * 0.01))
        )
    ]
    min_x_span = max(3, round(keyed_width / columns * 0.05))
    min_y_span = max(3, round(keyed_height / rows * 0.05))
    x_segments = [
        segment
        for segment in x_segments
        if segment[1] - segment[0] >= min_x_span
    ]
    y_segments = [
        segment
        for segment in y_segments
        if segment[1] - segment[0] >= min_y_span
    ]
    x_segments = merge_to_count(x_segments, columns)
    y_segments = merge_to_count(y_segments, rows)
    if len(x_segments) != columns or len(y_segments) != rows:
        raise ValueError(
            "Could not detect the expected sheet grid: "
            f"x={x_segments}, y={y_segments}, expected={columns}x{rows}"
        )
    return x_segments, y_segments


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--crop-x", type=int, default=180)
    parser.add_argument("--crop-y", type=int, default=40)
    parser.add_argument("--crop-width", type=int, default=210)
    parser.add_argument("--crop-height", type=int, default=110)
    parser.add_argument("--alpha-threshold", type=int, default=32)
    args = parser.parse_args()

    rows = (args.count + args.columns - 1) // args.columns
    sheet = Image.open(args.sheet).convert("RGBA")
    x_segments, y_segments = alpha_grid(
        sheet, args.columns, rows, args.alpha_threshold
    )
    expected_canvas = (412, 344)
    written: list[Path] = []

    for zero_index in range(args.count):
        number = zero_index + 1
        column = zero_index % args.columns
        row = zero_index // args.columns
        x0, x1 = x_segments[column]
        y0, y1 = y_segments[row]
        cell = sheet.crop((x0, y0, x1, y1)).resize(
            (args.crop_width, args.crop_height), Image.Resampling.LANCZOS
        )

        filename = f"Adventure_LEVEL{args.chapter}-{number}.png"
        source = args.source_dir / filename
        if not source.is_file():
            raise FileNotFoundError(source)
        original = Image.open(source).convert("RGBA")
        if original.size != expected_canvas:
            raise ValueError(
                f"Unexpected canvas for {source}: {original.size}, "
                f"expected {expected_canvas}"
            )

        # Replace the exact crop, including its transparent pixels. This keeps
        # the rest of the original level card byte-for-pixel untouched.
        original.paste(cell, (args.crop_x, args.crop_y))
        destination = args.output_dir / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        original.save(destination, optimize=True)
        written.append(destination)

    print(
        f"Applied generated sheet: chapter={args.chapter} files={len(written)} "
        f"grid={args.columns}x{rows} x_segments={x_segments} "
        f"y_segments={y_segments}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
