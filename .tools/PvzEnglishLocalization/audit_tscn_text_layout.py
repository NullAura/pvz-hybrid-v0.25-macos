#!/usr/bin/env python3
"""Flag localized Godot text that may overflow or cover an interactive control.

This is a conservative static audit. It only inspects text that changed between
the baseline and localized TSCN files, and it never edits scene geometry.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


NODE_RE = re.compile(r'^\[node name="((?:\\.|[^"])*)"(.*)\]$')
ATTRIBUTE_RE = re.compile(r'(\w+)="((?:\\.|[^"])*)"')
PROPERTY_RE = re.compile(r"^([^=]+?)\s*=\s*(.*)$")
VECTOR2_RE = re.compile(
    r"^Vector2\(\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)$"
)
NUMBER_RE = re.compile(r"^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$")
BB_CODE_RE = re.compile(r"\[(?:/?[a-zA-Z][^\]]*)\]")
INTERACTIVE_TYPES = {
    "BaseButton",
    "Button",
    "CheckBox",
    "CheckButton",
    "ColorPickerButton",
    "HScrollBar",
    "HSlider",
    "LineEdit",
    "LinkButton",
    "MenuButton",
    "OptionButton",
    "SpinBox",
    "TabBar",
    "TextEdit",
    "TextureButton",
    "Tree",
    "VScrollBar",
    "VSlider",
}
TEXT_PROPERTIES = {
    "text",
    "placeholder_text",
    "prefix",
    "suffix",
    "title",
}


@dataclass
class Node:
    name: str
    node_type: str
    parent: str
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> str:
        return f"{self.parent}/{self.name}".strip("/")


def decode_string(raw: str) -> str | None:
    if not raw.startswith('"'):
        return None
    try:
        return json.loads(raw.replace("\r", "\\r").replace("\n", "\\n"))
    except json.JSONDecodeError:
        return None


def parse_nodes(text: str) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    current: Node | None = None
    for line in text.splitlines():
        node_match = NODE_RE.match(line)
        if node_match:
            attributes = {
                key: json.loads(f'"{value}"')
                for key, value in ATTRIBUTE_RE.findall(node_match.group(2))
            }
            current = Node(
                name=json.loads(f'"{node_match.group(1)}"'),
                node_type=attributes.get("type", ""),
                parent=attributes.get("parent", ""),
            )
            nodes[current.path] = current
            continue
        if current is None or line.startswith("["):
            continue
        property_match = PROPERTY_RE.match(line)
        if property_match:
            current.properties[property_match.group(1).strip()] = (
                property_match.group(2).strip()
            )
    return nodes


def number(node: Node, key: str, default: float = 0.0) -> float:
    raw = node.properties.get(key)
    return float(raw) if raw and NUMBER_RE.match(raw) else default


def vector2(node: Node, key: str) -> tuple[float, float] | None:
    raw = node.properties.get(key, "")
    match = VECTOR2_RE.match(raw)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def local_rect(node: Node) -> tuple[float, float, float, float] | None:
    left = number(node, "offset_left")
    top = number(node, "offset_top")
    right = number(node, "offset_right")
    bottom = number(node, "offset_bottom")
    width = right - left
    height = bottom - top
    if width > 0 and height > 0:
        return left, top, right, bottom
    minimum = vector2(node, "custom_minimum_size")
    if minimum and minimum[0] > 0 and minimum[1] > 0:
        return left, top, left + minimum[0], top + minimum[1]
    size = vector2(node, "size")
    if size and size[0] > 0 and size[1] > 0:
        return left, top, left + size[0], top + size[1]
    return None


def font_size(node: Node) -> float:
    for key in (
        "theme_override_font_sizes/font_size",
        "theme_override_font_sizes/normal_font_size",
        "normal_font_size",
    ):
        value = number(node, key, -1)
        if value > 0:
            return value
    return 16.0


def outline_size(node: Node) -> float:
    return max(
        number(node, "theme_override_constants/outline_size"),
        number(node, "outline_size"),
    )


def strip_markup(text: str) -> str:
    return BB_CODE_RE.sub("", text).replace("\\n", "\n")


def glyph_units(text: str) -> float:
    units = 0.0
    for character in text:
        if character.isspace():
            units += 0.33
        elif unicodedata.east_asian_width(character) in {"F", "W"}:
            units += 1.0
        elif character in "ilI.,:;!'|`":
            units += 0.32
        elif character in "mwMW@%&#":
            units += 0.9
        elif character.isupper() or character.isdigit():
            units += 0.64
        else:
            units += 0.55
    return units


def estimated_text_width(text: str, node: Node) -> float:
    visible = strip_markup(text)
    line_units = max((glyph_units(line) for line in visible.splitlines()), default=0.0)
    return line_units * font_size(node) * 1.08 + outline_size(node) * 2.0


def is_wrapped(node: Node, text: str) -> bool:
    return (
        "\n" in text
        or node.node_type in {"RichTextLabel", "TextEdit"}
        or number(node, "autowrap_mode") > 0
    )


def rects_intersect(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
    padding: float = 1.0,
) -> bool:
    return not (
        first[2] <= second[0] + padding
        or first[0] >= second[2] - padding
        or first[3] <= second[1] + padding
        or first[1] >= second[3] - padding
    )


def predicted_text_rect(
    node: Node,
    rect: tuple[float, float, float, float],
    width: float,
) -> tuple[float, float, float, float]:
    left, top, right, bottom = rect
    alignment = int(number(node, "horizontal_alignment"))
    if alignment == 1:
        center = (left + right) / 2.0
        text_left = center - width / 2.0
    elif alignment == 2:
        text_left = right - width
    else:
        text_left = left
    text_height = min(
        bottom - top,
        font_size(node) * 1.25 + outline_size(node) * 2.0,
    )
    vertical_alignment = int(number(node, "vertical_alignment"))
    if vertical_alignment == 1:
        text_top = (top + bottom - text_height) / 2.0
    elif vertical_alignment == 2:
        text_top = bottom - text_height
    else:
        text_top = top
    return text_left, text_top, text_left + width, text_top + text_height


def interactive_rects(
    nodes: dict[str, Node],
    owner: Node,
) -> list[tuple[str, tuple[float, float, float, float]]]:
    results: list[tuple[str, tuple[float, float, float, float]]] = []
    for candidate in nodes.values():
        if candidate.node_type not in INTERACTIVE_TYPES:
            continue
        candidate_rect = local_rect(candidate)
        if candidate_rect is None:
            continue
        if candidate.parent == owner.path:
            owner_rect = local_rect(owner)
            if owner_rect is None:
                continue
            left, top, _, _ = owner_rect
            child = (
                left + candidate_rect[0],
                top + candidate_rect[1],
                left + candidate_rect[2],
                top + candidate_rect[3],
            )
            results.append((candidate.path, child))
        elif candidate.parent == owner.parent:
            results.append((candidate.path, candidate_rect))
    return results


def audit_scene(
    relative_path: str,
    original_text: str,
    localized_text: str,
) -> list[dict[str, object]]:
    original_nodes = parse_nodes(original_text)
    localized_nodes = parse_nodes(localized_text)
    findings: list[dict[str, object]] = []
    for path, localized in localized_nodes.items():
        original = original_nodes.get(path)
        if original is None:
            continue
        rect = local_rect(localized)
        for property_name in TEXT_PROPERTIES:
            source = decode_string(original.properties.get(property_name, ""))
            target = decode_string(localized.properties.get(property_name, ""))
            if source is None or target is None or source == target or not target:
                continue
            if is_wrapped(localized, target):
                continue
            width = estimated_text_width(target, localized)
            source_width = estimated_text_width(source, original)
            source_ratio = (
                source_width / (local_rect(original)[2] - local_rect(original)[0])
                if local_rect(original) is not None
                and local_rect(original)[2] > local_rect(original)[0]
                else None
            )
            footprint_expanded = width > source_width * 1.05
            reasons: list[str] = []
            available: float | None = None
            text_rect: tuple[float, float, float, float] | None = None
            if rect is not None:
                available = rect[2] - rect[0]
                if localized.node_type in INTERACTIVE_TYPES:
                    available = max(0.0, available - 16.0)
                text_rect = predicted_text_rect(localized, rect, width)
                interactions = interactive_rects(localized_nodes, localized)
                has_direct_interactive_child = any(
                    interactive_path.startswith(f"{localized.path}/")
                    for interactive_path, _ in interactions
                )
                if not has_direct_interactive_child:
                    if width > available and (
                        source_ratio is None
                        or source_ratio <= 1.0
                        or footprint_expanded
                    ):
                        reasons.append("overflow")
                    elif (
                        available > 0
                        and width / available >= 0.86
                        and (
                            source_ratio is None
                            or source_ratio < 0.86
                            or footprint_expanded
                        )
                    ):
                        reasons.append("tight")
                if localized.node_type not in INTERACTIVE_TYPES:
                    for interactive_path, interactive_rect in interactions:
                        source_rect = local_rect(original)
                        original_text_rect = (
                            predicted_text_rect(original, source_rect, source_width)
                            if source_rect is not None
                            else None
                        )
                        original_overlap = (
                            original_text_rect is not None
                            and rects_intersect(
                                original_text_rect,
                                interactive_rect,
                            )
                        )
                        if (
                            text_rect
                            and rects_intersect(text_rect, interactive_rect)
                            and not original_overlap
                        ):
                            reasons.append(f"covers:{interactive_path}")
            ratio = width / source_width if source_width > 0 else math.inf
            if ratio >= 1.8 and rect is None:
                reasons.append("expanded-without-fixed-width")
            if not reasons:
                continue
            findings.append(
                {
                    "resource": relative_path,
                    "node": path,
                    "type": localized.node_type,
                    "property": property_name,
                    "source": source,
                    "target": target,
                    "font_size": font_size(localized),
                    "estimated_width": round(width, 2),
                    "available_width": (
                        round(available, 2) if available is not None else None
                    ),
                    "source_width_ratio": (
                        round(ratio, 2) if math.isfinite(ratio) else None
                    ),
                    "reasons": sorted(set(reasons)),
                }
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--localized-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    findings: list[dict[str, object]] = []
    advisories: list[dict[str, object]] = []
    scene_count = 0
    for localized_path in sorted(args.localized_root.rglob("*.tscn")):
        relative_path = localized_path.relative_to(args.localized_root)
        original_path = args.original_root / relative_path
        if not original_path.is_file():
            continue
        scene_count += 1
        scene_results = audit_scene(
            relative_path.as_posix(),
            original_path.read_text(encoding="utf-8-sig"),
            localized_path.read_text(encoding="utf-8-sig"),
        )
        for result in scene_results:
            if result["reasons"] == ["expanded-without-fixed-width"]:
                advisories.append(result)
            else:
                findings.append(result)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "scenes": scene_count,
                "findings": findings,
                "advisories": advisories,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Audited localized TSCNs: scenes={scene_count} "
        f"findings={len(findings)} advisories={len(advisories)}"
    )
    for finding in findings:
        reasons = ",".join(finding["reasons"])
        print(
            f"{reasons}\t{finding['resource']}\t{finding['node']}\t"
            f"{finding['target']!r}\t{finding['estimated_width']}/"
            f"{finding['available_width']}"
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
