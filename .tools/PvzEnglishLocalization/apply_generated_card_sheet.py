#!/usr/bin/env python3
"""Patch one generated title sheet into exact original level-card canvases."""

from __future__ import annotations

import argparse
import json
import math
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from apply_generated_level_sheet import alpha_grid


def parse_box(value: str) -> tuple[int, int, int, int]:
    try:
        parts = tuple(int(part) for part in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "box must be x,y,width,height"
        ) from error
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise argparse.ArgumentTypeError("box must be x,y,width,height")
    return parts


def remove_magenta_key(
    image: Image.Image,
    inner_tolerance: float = 36.0,
    outer_tolerance: float = 118.0,
) -> Image.Image:
    """Convert generated magenta gutters and their fringe to transparency."""
    rgba = image.convert("RGBA")
    output: list[tuple[int, int, int, int]] = []
    for red, green, blue, alpha in rgba.get_flattened_data():
        distance = math.sqrt(
            (red - 255) ** 2 + green**2 + (blue - 255) ** 2
        )
        # The edit model can antialias a black card edge against the magenta
        # sheet, producing a dark-purple fringe far outside a simple RGB
        # distance threshold. Remove that spill without touching red flags,
        # blue night art, or pink highlights inside the card.
        dark_magenta_spill = (
            green <= 48
            and min(red, blue) >= 64
            and abs(red - blue) <= 58
        )
        if distance <= inner_tolerance or dark_magenta_spill:
            keyed_alpha = 0
        elif distance < outer_tolerance:
            keyed_alpha = round(
                alpha
                * (distance - inner_tolerance)
                / (outer_tolerance - inner_tolerance)
            )
        else:
            keyed_alpha = alpha
        if keyed_alpha == 0:
            output.append((0, 0, 0, 0))
        else:
            output.append((red, green, blue, keyed_alpha))
    rgba.putdata(output)
    return rgba


def edge_feather_mask(
    size: tuple[int, int], feather: int, feather_right: bool
) -> Image.Image:
    """Create a soft crop mask without leaving a rectangular edit edge."""
    width, height = size
    if feather <= 0:
        return Image.new("L", size, 255)
    values: list[int] = []
    for y in range(height):
        for x in range(width):
            distances = [x, y, height - 1 - y]
            if feather_right:
                distances.append(width - 1 - x)
            distance = min(distances)
            values.append(min(255, round(255 * distance / feather)))
    mask = Image.new("L", size)
    mask.putdata(values)
    return mask


def fill_keyed_text_holes(
    generated: Image.Image,
    original_alpha: Image.Image,
    text_boxes: list[tuple[int, int, int, int]],
    crop_box: tuple[int, int, int, int],
) -> Image.Image:
    """Fill keyed pixels inside original text boxes from nearest generated art.

    Edit models occasionally echo the sheet's magenta gutter into a few glyph
    pixels. Once keyed, those pixels would reveal fragments of the original
    Chinese text. Filling only the keyed glyph-area pixels from their nearest
    valid generated neighbour preserves the image-generated background without
    introducing a rectangular patch or changing any pixels outside text.
    """
    if not text_boxes:
        return generated
    left, top, _, _ = crop_box
    width, height = generated.size
    rgba = generated.convert("RGBA")
    pixels = list(rgba.get_flattened_data())
    alpha_values = list(rgba.getchannel("A").get_flattened_data())
    original_alpha_values = list(original_alpha.get_flattened_data())
    targets = bytearray(width * height)
    # Chinese title/subtitle glyphs frequently touch the angled outer ribbon
    # beyond Vision's tight box. Extend only the *hole-selection* region; the
    # fill remains pixel-shaped and applies solely where chroma keying removed
    # generated pixels.
    padding = 20
    for box_left, box_top, box_width, box_height in text_boxes:
        relative_left = max(0, box_left - left - padding)
        relative_top = max(0, box_top - top - padding)
        relative_right = min(
            width,
            box_left - left + box_width + padding,
        )
        relative_bottom = min(
            height,
            box_top - top + box_height + padding,
        )
        if (
            relative_right <= relative_left
            or relative_bottom <= relative_top
        ):
            continue
        for y in range(relative_top, relative_bottom):
            offset = y * width
            for x in range(relative_left, relative_right):
                index = offset + x
                if (
                    alpha_values[index] == 0
                    and original_alpha_values[index] > 0
                ):
                    targets[index] = 1
    if not any(targets):
        return rgba

    queue: deque[int] = deque()
    owner = [-1] * (width * height)
    for index, alpha in enumerate(alpha_values):
        if alpha > 0:
            owner[index] = index
            queue.append(index)
    while queue:
        index = queue.popleft()
        x = index % width
        y = index // width
        neighbours: list[int] = []
        if x > 0:
            neighbours.append(index - 1)
        if x + 1 < width:
            neighbours.append(index + 1)
        if y > 0:
            neighbours.append(index - width)
        if y + 1 < height:
            neighbours.append(index + width)
        for neighbour in neighbours:
            if owner[neighbour] == -1:
                owner[neighbour] = owner[index]
                queue.append(neighbour)
    for index, is_target in enumerate(targets):
        if not is_target:
            continue
        source_index = owner[index]
        if source_index < 0:
            continue
        red, green, blue, _ = pixels[source_index]
        pixels[index] = (
            red,
            green,
            blue,
            original_alpha_values[index],
        )
    rgba.putdata(pixels)
    return rgba


def clear_isolated_right_components(
    image: Image.Image,
    x_threshold: int = 380,
    x_max: int | None = None,
    y_min: int = 55,
    y_max: int = 170,
) -> Image.Image:
    """Remove detached title remnants confined to the outer right margin."""
    rgba = image.convert("RGBA")
    width, height = rgba.size
    alpha_values = list(rgba.getchannel("A").get_flattened_data())
    visited = bytearray(width * height)
    clear_indices: list[int] = []
    for start, alpha in enumerate(alpha_values):
        if alpha == 0 or visited[start]:
            continue
        queue: deque[int] = deque([start])
        visited[start] = 1
        component: list[int] = []
        reaches_body = False
        touches_cleanup_band = False
        while queue:
            index = queue.popleft()
            component.append(index)
            x = index % width
            y = index // width
            if x < x_threshold:
                reaches_body = True
            if x >= x_threshold and y_min <= y < y_max:
                touches_cleanup_band = True
            for neighbour in (
                index - 1 if x > 0 else -1,
                index + 1 if x + 1 < width else -1,
                index - width if y > 0 else -1,
                index + width if y + 1 < height else -1,
            ):
                if (
                    neighbour >= 0
                    and not visited[neighbour]
                    and alpha_values[neighbour] > 0
                ):
                    visited[neighbour] = 1
                    queue.append(neighbour)
        if touches_cleanup_band and not reaches_body:
            clear_indices.extend(
                index
                for index in component
                if x_max is None or index % width < x_max
            )
    if not clear_indices:
        return rgba
    pixels = list(rgba.get_flattened_data())
    for index in clear_indices:
        pixels[index] = (0, 0, 0, 0)
    rgba.putdata(pixels)
    return rgba


def composite_generated_crop(
    original: Image.Image,
    generated: Image.Image,
    crop_box: tuple[int, int, int, int],
    feather: int,
    preserve_border: int,
    text_boxes: list[tuple[int, int, int, int]],
    fill_hole_boxes: list[tuple[int, int, int, int]],
    clear_uncovered_boxes: list[tuple[int, int, int, int]],
) -> Image.Image:
    """Blend one generated crop while retaining the original outer border."""
    left, top, right, bottom = crop_box
    original_crop = original.crop(crop_box).convert("RGBA")
    generated = remove_magenta_key(generated)
    generated = fill_keyed_text_holes(
        generated,
        original_crop.getchannel("A"),
        fill_hole_boxes,
        crop_box,
    )
    generated_alpha = generated.getchannel("A")
    mask = generated_alpha
    feather_mask = edge_feather_mask(
        generated.size,
        feather,
        # The standard card crop ends at x=411 on canvases that are 411 or
        # 412 pixels wide. Treat that as the outer edge; feathering the final
        # 12 pixels used to reveal trailing Chinese numerals on the ribbon.
        feather_right=right + feather < original.width,
    )
    mask = ImageChops.multiply(mask, feather_mask)
    if preserve_border > 0:
        filter_size = preserve_border * 2 + 1
        original_alpha = original_crop.getchannel("A")
        interior = original_alpha.filter(ImageFilter.MinFilter(filter_size))
        interior = interior.filter(
            ImageFilter.GaussianBlur(radius=max(1, preserve_border / 2))
        )
        mask = ImageChops.multiply(mask, interior)
    if text_boxes:
        text_override = Image.new("L", generated.size, 0)
        draw = ImageDraw.Draw(text_override)
        # OCR boxes are tight vertically, while display-glyph antialiasing can
        # extend farther at the left and right. Keep the vertical expansion
        # small so a nearby original card outline is never replaced.
        padding_x = max(6, preserve_border + 2)
        padding_y = 3
        for box_left, box_top, box_width, box_height in text_boxes:
            relative_left = box_left - left
            relative_top = box_top - top
            relative_right = relative_left + box_width
            relative_bottom = relative_top + box_height
            if (
                relative_right <= 0
                or relative_bottom <= 0
                or relative_left >= generated.width
                or relative_top >= generated.height
            ):
                continue
            draw.rounded_rectangle(
                (
                    max(0, relative_left - padding_x),
                    max(0, relative_top - padding_y),
                    min(generated.width, relative_right + padding_x),
                    min(generated.height, relative_bottom + padding_y),
                ),
                radius=3,
                fill=255,
            )
        text_override = text_override.filter(ImageFilter.GaussianBlur(1))
        mask = ImageChops.lighter(mask, text_override)
    # OCR/forced overrides may relax feathering and border preservation, but
    # they must never revive pixels removed by chroma keying. Reapply source
    # alpha last so keyed gutters remain a transparent *layer mask* and reveal
    # the exact original underneath instead of punching holes through it.
    mask = ImageChops.multiply(mask, generated_alpha)
    composed_crop = Image.composite(generated, original_crop, mask)
    if clear_uncovered_boxes:
        composed_pixels = list(composed_crop.get_flattened_data())
        generated_alpha_values = list(
            generated_alpha.get_flattened_data()
        )
        for box_left, box_top, box_width, box_height in clear_uncovered_boxes:
            relative_left = max(0, box_left - left)
            relative_top = max(0, box_top - top)
            relative_right = min(
                generated.width,
                box_left - left + box_width,
            )
            relative_bottom = min(
                generated.height,
                box_top - top + box_height,
            )
            for y in range(relative_top, relative_bottom):
                offset = y * generated.width
                for x in range(relative_left, relative_right):
                    index = offset + x
                    if generated_alpha_values[index] == 0:
                        composed_pixels[index] = (0, 0, 0, 0)
        composed_crop.putdata(composed_pixels)
    # Never key the composed crop a second time: it already contains exact
    # original artwork, and legitimate night/purple pixels can resemble the
    # chroma key. The generated layer was keyed before it entered the blend.
    result = original.copy()
    result.paste(composed_crop, (left, top))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--sheet", type=Path, required=True)
    parser.add_argument("--gui-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--crop-x", type=int, default=180)
    parser.add_argument("--crop-y", type=int, default=40)
    parser.add_argument("--crop-width", type=int, default=210)
    parser.add_argument("--crop-height", type=int, default=110)
    parser.add_argument("--alpha-threshold", type=int, default=32)
    parser.add_argument(
        "--feather",
        type=int,
        default=0,
        help="Soft crop-edge blend in pixels.",
    )
    parser.add_argument(
        "--preserve-border",
        type=int,
        default=0,
        help="Retain this many pixels of the original alpha silhouette.",
    )
    parser.add_argument(
        "--ocr-report",
        type=Path,
        help="OCR JSON whose source-text boxes override border preservation.",
    )
    parser.add_argument(
        "--force-text-box",
        type=parse_box,
        action="append",
        default=[],
        help="Full-card text region to clean even when OCR misses it.",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        help="Per-card uncovered-pixel cleanup boxes.",
    )
    args = parser.parse_args()

    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    overrides: dict[str, dict[str, list[list[int]]]] = {}
    if args.overrides:
        overrides = json.loads(args.overrides.read_text(encoding="utf-8"))
    ocr_boxes_by_path: dict[str, list[tuple[int, int, int, int]]] = {}
    if args.ocr_report:
        ocr_report = json.loads(args.ocr_report.read_text(encoding="utf-8"))
        for ocr_record in ocr_report["records"]:
            boxes = [
                tuple(map(int, box["box"]))
                for box in ocr_record.get("boxes", [])
            ]
            if boxes:
                ocr_boxes_by_path[str(ocr_record["path"])] = boxes
    records = batch["records"]
    columns = int(batch["columns"])
    rows = int(batch["rows"])
    sheet = Image.open(args.sheet).convert("RGBA")
    detected_columns = min(columns, len(records))
    x_segments, y_segments = alpha_grid(
        sheet, detected_columns, rows, args.alpha_threshold
    )
    written: list[str] = []
    for index, record in enumerate(records):
        column = index % columns
        row = index // columns
        x0, x1 = x_segments[column]
        y0, y1 = y_segments[row]
        cell = sheet.crop((x0, y0, x1, y1)).resize(
            (args.crop_width, args.crop_height),
            Image.Resampling.LANCZOS,
        )
        relative = Path(record["path"])
        override = overrides.get(relative.as_posix(), {})
        clear_uncovered_boxes = [
            tuple(map(int, box))
            for box in override.get(
                "clear_uncovered_boxes",
                [],
            )
        ]
        # Generated blank sheets define the true card silhouette at the outer
        # title edge. Original Chinese glyphs often protrude beyond it, so do
        # not preserve uncovered source pixels in the final 32 columns.
        clear_uncovered_boxes.append((380, 55, 32, 115))
        source_path = args.gui_root / relative
        original = Image.open(source_path).convert("RGBA")
        if (
            original.width < args.crop_x + args.crop_width
            or original.height < args.crop_y + args.crop_height
        ):
            raise ValueError(
                f"Title crop exceeds canvas for {source_path}: "
                f"{original.size}"
            )
        if args.feather > 0 or args.preserve_border > 0:
            original = composite_generated_crop(
                original,
                cell,
                (
                    args.crop_x,
                    args.crop_y,
                    args.crop_x + args.crop_width,
                    args.crop_y + args.crop_height,
                ),
                args.feather,
                args.preserve_border,
                (
                    ocr_boxes_by_path.get(relative.as_posix(), [])
                    + args.force_text_box
                ),
                ocr_boxes_by_path.get(relative.as_posix(), []),
                clear_uncovered_boxes,
            )
        else:
            original.paste(remove_magenta_key(cell), (args.crop_x, args.crop_y))
        original = clear_isolated_right_components(
            original,
            x_max=args.crop_x + args.crop_width,
        )
        output_path = args.output_root / relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        original.save(output_path, optimize=True)
        written.append(relative.as_posix())

    print(
        f"Applied generated card sheet: batch={batch['batch_index']} "
        f"files={len(written)} grid={columns}x{rows} "
        f"x_segments={x_segments} y_segments={y_segments}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
