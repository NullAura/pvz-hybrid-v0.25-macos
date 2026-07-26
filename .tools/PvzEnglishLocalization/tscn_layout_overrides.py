#!/usr/bin/env python3
"""Apply declared, text-only layout overrides to Godot text scenes."""

from __future__ import annotations

import json
from pathlib import Path
import re


NODE_HEADER_RE = re.compile(r"^\[node (?P<body>.*)\]\n?$")
ATTRIBUTE_RE = re.compile(
    r'(?P<key>[A-Za-z0-9_]+)=(?P<value>"(?:\\.|[^"\\])*"|[^\s]+)'
)
ALLOWED_PROPERTIES = {
    "anchors_preset",
    "anchor_right",
    "anchor_bottom",
    "offset_left",
    "offset_right",
    "offset_bottom",
    "grow_horizontal",
    "grow_vertical",
    "theme_override_font_sizes/font_size",
    "theme_override_font_sizes/normal_font_size",
}


def load_layout_overrides(
    path: Path | None,
) -> dict[str, dict[str, dict[str, str]]]:
    if path is None:
        return {}
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"layout overrides must be an object: {path}")

    result: dict[str, dict[str, dict[str, str]]] = {}
    for resource_path, nodes in parsed.items():
        if not isinstance(resource_path, str) or not isinstance(nodes, dict):
            raise ValueError(f"invalid resource entry in layout overrides: {path}")
        normalized_resource = resource_path.removeprefix("res://").lstrip("/")
        result[normalized_resource] = {}
        for node_path, properties in nodes.items():
            if not isinstance(node_path, str) or not isinstance(properties, dict):
                raise ValueError(
                    f"{normalized_resource}: invalid node override {node_path!r}"
                )
            checked: dict[str, str] = {}
            for property_name, raw_value in properties.items():
                if property_name not in ALLOWED_PROPERTIES:
                    raise ValueError(
                        f"{normalized_resource}:{node_path}: "
                        f"property is not text-layout-only: {property_name}"
                    )
                if not isinstance(raw_value, str) or "\n" in raw_value:
                    raise ValueError(
                        f"{normalized_resource}:{node_path}: "
                        f"override value must be one line of Godot syntax"
                    )
                checked[property_name] = raw_value
            result[normalized_resource][node_path] = checked
    return result


def _decode_attribute(raw: str) -> str:
    return json.loads(raw) if raw.startswith('"') else raw


def _node_path(header_line: str, is_first_node: bool) -> str | None:
    match = NODE_HEADER_RE.match(header_line)
    if match is None:
        return None
    attributes = {
        item.group("key"): item.group("value")
        for item in ATTRIBUTE_RE.finditer(match.group("body"))
    }
    name_raw = attributes.get("name")
    if name_raw is None:
        return None
    name = _decode_attribute(name_raw)
    parent_raw = attributes.get("parent")
    if parent_raw is None:
        return "." if is_first_node else name
    parent = _decode_attribute(parent_raw)
    return name if parent == "." else f"{parent}/{name}"


def apply_layout_overrides(
    text: str,
    resource_path: str,
    overrides: dict[str, dict[str, dict[str, str]]],
) -> tuple[str, int]:
    resource_overrides = overrides.get(resource_path)
    if not resource_overrides:
        return text, 0

    lines = text.splitlines(keepends=True)
    header_indices = [
        index for index, line in enumerate(lines) if line.startswith("[")
    ]
    header_indices.append(len(lines))
    first_node_header = next(
        (
            index
            for index in header_indices[:-1]
            if lines[index].startswith("[node ")
        ),
        -1,
    )
    found: set[str] = set()
    changes = 0

    for header_index, next_header_index in reversed(
        list(zip(header_indices[:-1], header_indices[1:], strict=True))
    ):
        header = lines[header_index]
        if not header.startswith("[node "):
            continue
        node_path = _node_path(header, header_index == first_node_header)
        if node_path not in resource_overrides:
            continue
        found.add(node_path)
        properties = resource_overrides[node_path]
        block = lines[header_index + 1 : next_header_index]
        for property_name, raw_value in properties.items():
            replacement = f"{property_name} = {raw_value}\n"
            property_index = next(
                (
                    index
                    for index, line in enumerate(block)
                    if line.startswith(f"{property_name} = ")
                ),
                None,
            )
            if property_index is not None:
                if block[property_index] != replacement:
                    block[property_index] = replacement
                    changes += 1
                continue

            insertion_index = len(block)
            while insertion_index and not block[insertion_index - 1].strip():
                insertion_index -= 1
            block.insert(insertion_index, replacement)
            changes += 1
        lines[header_index + 1 : next_header_index] = block

    missing = set(resource_overrides) - found
    if missing:
        raise ValueError(
            f"{resource_path}: layout override node(s) not found: "
            + ", ".join(sorted(missing))
        )
    return "".join(lines), changes
