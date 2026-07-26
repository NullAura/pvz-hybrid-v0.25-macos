#!/usr/bin/env python3
"""Verify that a localized PCK changes only declared text and image resources.

The audit compares PCK directory digests, replays every exact-string replacement
and declared text-only layout override, rejects translated Godot scene section
headers, and can stream-verify every stored payload against its PCK MD5. It is
designed to make interaction parity testable: undeclared scene, signal,
interactive geometry, animation, audio, input, and gameplay-resource changes
fail the audit.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import BinaryIO, Iterable

from tscn_layout_overrides import (
    apply_layout_overrides,
    load_layout_overrides,
)


PCK_MAGIC = b"GDPC"
MIN_HEADER_SIZE = 112
READ_SIZE = 1024 * 1024
QUOTED_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
SECTION_RE = re.compile(r"^\[(?P<kind>[a-z_]+)(?: (?P<body>.*))?\]$")
ATTRIBUTE_RE = re.compile(
    r'(?P<key>[A-Za-z0-9_]+)=(?P<value>"(?:\\.|[^"\\])*"|[^\s]+)'
)
DISPLAY_NAME_PARENT_TYPES = {"MenuBar", "TabContainer"}


@dataclass(frozen=True)
class Entry:
    path: str
    offset: int
    size: int
    digest: bytes
    flags: int


@dataclass(frozen=True)
class Pack:
    path: Path
    file_base: int
    entries: dict[str, Entry]


def read_exact(handle: BinaryIO, size: int) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise ValueError(f"unexpected EOF: wanted {size} bytes, got {len(data)}")
    return data


def read_u32(handle: BinaryIO) -> int:
    return struct.unpack("<I", read_exact(handle, 4))[0]


def read_u64(handle: BinaryIO) -> int:
    return struct.unpack("<Q", read_exact(handle, 8))[0]


def read_pack(path: Path) -> Pack:
    file_size = path.stat().st_size
    with path.open("rb") as handle:
        header = read_exact(handle, MIN_HEADER_SIZE)
        if header[:4] != PCK_MAGIC:
            raise ValueError(f"not a standalone Godot PCK: {path}")
        pack_format = struct.unpack_from("<I", header, 4)[0]
        if pack_format not in (2, 3, 4):
            raise ValueError(f"unsupported PCK format {pack_format}: {path}")
        file_base = struct.unpack_from("<Q", header, 24)[0]
        directory_offset = struct.unpack_from("<Q", header, 32)[0]
        if not (
            MIN_HEADER_SIZE <= file_base <= directory_offset < file_size
        ):
            raise ValueError(
                "invalid PCK offsets: "
                f"file_base={file_base}, directory_offset={directory_offset}, "
                f"file_size={file_size}"
            )

        handle.seek(directory_offset)
        count = read_u32(handle)
        if count > 10_000_000:
            raise ValueError(f"implausible PCK entry count: {count}")
        entries: dict[str, Entry] = {}
        for index in range(count):
            path_size = read_u32(handle)
            if path_size == 0 or path_size > 1_048_576:
                raise ValueError(
                    f"invalid path size for entry {index}: {path_size}"
                )
            path_raw = read_exact(handle, path_size)
            try:
                entry_path = path_raw.rstrip(b"\0").decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError(
                    f"entry {index} has a non-UTF-8 path"
                ) from error
            offset = read_u64(handle)
            size = read_u64(handle)
            digest = read_exact(handle, 16)
            flags = read_u32(handle)
            if entry_path in entries:
                raise ValueError(f"duplicate PCK path: {entry_path}")
            absolute_offset = file_base + offset
            if absolute_offset < file_base or absolute_offset + size > file_size:
                raise ValueError(f"entry is outside the PCK: {entry_path}")
            entries[entry_path] = Entry(
                path=entry_path,
                offset=offset,
                size=size,
                digest=digest,
                flags=flags,
            )
    return Pack(path=path, file_base=file_base, entries=entries)


def read_payload(pack: Pack, entry: Entry) -> bytes:
    with pack.path.open("rb") as handle:
        handle.seek(pack.file_base + entry.offset)
        return read_exact(handle, entry.size)


def verify_payloads(pack: Pack) -> None:
    with pack.path.open("rb") as handle:
        for entry in pack.entries.values():
            handle.seek(pack.file_base + entry.offset)
            digest = hashlib.md5()
            remaining = entry.size
            while remaining:
                chunk = read_exact(handle, min(READ_SIZE, remaining))
                digest.update(chunk)
                remaining -= len(chunk)
            if digest.digest() != entry.digest:
                raise ValueError(
                    f"stored payload MD5 mismatch in {pack.path}: {entry.path}"
                )


def load_string_map(path: Path) -> dict[str, str]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in parsed.items()
    ):
        raise ValueError(f"expected a string dictionary: {path}")
    return parsed


def decode_literal(raw: str) -> str:
    return json.loads(raw.replace("\r", "\\r").replace("\n", "\\n"))


def replace_quoted_strings(
    text: str,
    translations: dict[str, str],
) -> tuple[str, int]:
    replacements = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements
        try:
            source = decode_literal(match.group(0))
        except json.JSONDecodeError:
            return match.group(0)
        translated = translations.get(source)
        if translated is None or translated == source:
            return match.group(0)

        replacements += 1
        return json.dumps(translated, ensure_ascii=False)

    return QUOTED_STRING_RE.sub(replace, text), replacements


def parse_header_attributes(body: str) -> dict[str, str]:
    attributes = {
        match.group("key"): match.group("value")
        for match in ATTRIBUTE_RE.finditer(body)
    }
    consumed = ATTRIBUTE_RE.sub("", body).strip()
    if consumed:
        raise ValueError(f"could not parse section attributes: {body}")
    return attributes


def decode_attribute(value: str) -> str:
    return decode_literal(value) if value.startswith('"') else value


def section_header_lines(text: str) -> list[str]:
    headers: list[str] = []
    in_string = False
    escaped = False
    for line in text.splitlines():
        if not in_string and line.startswith("[") and line.endswith("]"):
            headers.append(line)
        for character in line:
            if escaped:
                escaped = False
                continue
            if character == "\\" and in_string:
                escaped = True
                continue
            if character == '"':
                in_string = not in_string
        escaped = False
    if in_string:
        raise ValueError("unterminated quoted string in Godot text resource")
    return headers


def parse_tscn_structure(
    text: str,
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[tuple[str, dict[str, str]]],
]:
    nodes: list[dict[str, str]] = []
    connections: list[dict[str, str]] = []
    other_headers: list[tuple[str, dict[str, str]]] = []
    for line in section_header_lines(text):
        match = SECTION_RE.match(line)
        if match is None:
            continue
        kind = match.group("kind")
        attributes = parse_header_attributes(match.group("body") or "")
        if kind == "node":
            nodes.append(attributes)
        elif kind == "connection":
            connections.append(attributes)
        else:
            other_headers.append((kind, attributes))
    return nodes, connections, other_headers


def resolve_node_tree(
    nodes: list[dict[str, str]],
) -> tuple[list[int | None], dict[str, int], list[str]]:
    parent_indices: list[int | None] = []
    paths: dict[str, int] = {}
    node_types: list[str] = []
    for index, node in enumerate(nodes):
        name = decode_attribute(node.get("name", '""'))
        node_type = decode_attribute(node.get("type", '""'))
        node_types.append(node_type)
        if index == 0:
            if "parent" in node:
                raise ValueError("root node unexpectedly has a parent")
            parent_indices.append(None)
            paths["."] = index
            continue

        if "parent" not in node:
            raise ValueError(f"node has no parent: {name}")
        parent_path = decode_attribute(node["parent"])
        if parent_path not in paths:
            raise ValueError(
                f"node parent does not resolve: {name} -> {parent_path}"
            )
        parent_indices.append(paths[parent_path])
        node_path = name if parent_path == "." else f"{parent_path}/{name}"
        if node_path in paths:
            raise ValueError(f"duplicate node path: {node_path}")
        paths[node_path] = index
    return parent_indices, paths, node_types


def resolve_path(path: str, paths: dict[str, int]) -> int:
    if path not in paths:
        raise ValueError(f"node path does not resolve: {path}")
    return paths[path]


def verify_tscn_structure(
    baseline_text: str,
    localized_text: str,
    translations: dict[str, str],
    resource_path: str,
) -> None:
    baseline_headers = section_header_lines(baseline_text)
    localized_headers = section_header_lines(localized_text)
    if baseline_headers == localized_headers:
        return

    baseline_nodes, baseline_connections, baseline_other = (
        parse_tscn_structure(baseline_text)
    )
    localized_nodes, localized_connections, localized_other = (
        parse_tscn_structure(localized_text)
    )
    if len(baseline_nodes) != len(localized_nodes):
        raise ValueError(
            f"{resource_path}: node count changed "
            f"{len(baseline_nodes)} -> {len(localized_nodes)}"
        )
    if len(baseline_connections) != len(localized_connections):
        raise ValueError(
            f"{resource_path}: connection count changed "
            f"{len(baseline_connections)} -> {len(localized_connections)}"
        )
    if baseline_other != localized_other:
        raise ValueError(f"{resource_path}: non-node section headers changed")

    baseline_parents, baseline_paths, baseline_types = resolve_node_tree(
        baseline_nodes
    )
    localized_parents, localized_paths, localized_types = resolve_node_tree(
        localized_nodes
    )
    if baseline_parents != localized_parents:
        raise ValueError(f"{resource_path}: node hierarchy changed")
    if baseline_types != localized_types:
        raise ValueError(f"{resource_path}: node types changed")

    for index, (baseline_node, localized_node) in enumerate(
        zip(baseline_nodes, localized_nodes, strict=True)
    ):
        baseline_name = decode_attribute(baseline_node.get("name", '""'))
        localized_name = decode_attribute(localized_node.get("name", '""'))
        if baseline_name != localized_name:
            parent_index = baseline_parents[index]
            parent_type = (
                baseline_types[parent_index]
                if parent_index is not None
                else ""
            )
            expected_name = translations.get(baseline_name, baseline_name)
            if (
                parent_type not in DISPLAY_NAME_PARENT_TYPES
                or localized_name != expected_name
            ):
                raise ValueError(
                    f"{resource_path}: internal node name changed: "
                    f"{baseline_name} -> {localized_name}"
                )

        ignored = {"name", "parent", "owner"}
        baseline_identity = {
            key: value
            for key, value in baseline_node.items()
            if key not in ignored
        }
        localized_identity = {
            key: value
            for key, value in localized_node.items()
            if key not in ignored
        }
        if baseline_identity != localized_identity:
            raise ValueError(
                f"{resource_path}: node identity changed at index {index}"
            )

        for path_key in ("owner",):
            baseline_value = baseline_node.get(path_key)
            localized_value = localized_node.get(path_key)
            if (baseline_value is None) != (localized_value is None):
                raise ValueError(
                    f"{resource_path}: node {path_key} presence changed"
                )
            if baseline_value is not None and localized_value is not None:
                baseline_index = resolve_path(
                    decode_attribute(baseline_value), baseline_paths
                )
                localized_index = resolve_path(
                    decode_attribute(localized_value), localized_paths
                )
                if baseline_index != localized_index:
                    raise ValueError(
                        f"{resource_path}: node {path_key} target changed"
                    )

    for index, (baseline_connection, localized_connection) in enumerate(
        zip(
            baseline_connections,
            localized_connections,
            strict=True,
        )
    ):
        for path_key in ("from", "to"):
            baseline_index = resolve_path(
                decode_attribute(baseline_connection[path_key]),
                baseline_paths,
            )
            localized_index = resolve_path(
                decode_attribute(localized_connection[path_key]),
                localized_paths,
            )
            if baseline_index != localized_index:
                raise ValueError(
                    f"{resource_path}: connection {index} {path_key} changed"
                )
        ignored = {"from", "to"}
        baseline_identity = {
            key: value
            for key, value in baseline_connection.items()
            if key not in ignored
        }
        localized_identity = {
            key: value
            for key, value in localized_connection.items()
            if key not in ignored
        }
        if baseline_identity != localized_identity:
            raise ValueError(
                f"{resource_path}: connection {index} signal or method changed"
            )


def load_resource_manifest(
    path: Path,
) -> tuple[dict[str, int], set[str], set[str]]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    files = parsed.get("files")
    if not isinstance(files, list):
        raise ValueError(f"resource manifest has no files list: {path}")

    counts: dict[str, int] = {}
    changed: set[str] = set()
    added: set[str] = set()
    for item in files:
        resource_path = str(item["path"])
        counts[resource_path] = int(item["replacements"])
        if resource_path == "project.godot":
            added.add("project.godot")
            changed.add("project.binary")
        else:
            changed.add(resource_path)
    return counts, changed, added


def load_graphic_report(path: Path) -> set[str]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    patched = parsed.get("patched")
    if not isinstance(patched, list):
        raise ValueError(f"graphic patch report has no patched list: {path}")
    return {str(item["path"]) for item in patched}


def format_paths(paths: Iterable[str], limit: int = 30) -> str:
    values = sorted(paths)
    shown = values[:limit]
    suffix = (
        f"\n  ... {len(values) - limit} additional path(s)"
        if len(values) > limit
        else ""
    )
    return "\n  " + "\n  ".join(shown) + suffix if values else " none"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-pck", required=True, type=Path)
    parser.add_argument("--localized-pck", required=True, type=Path)
    parser.add_argument("--translations", required=True, type=Path)
    parser.add_argument("--layout-overrides", type=Path)
    parser.add_argument("--resource-manifest", required=True, type=Path)
    parser.add_argument("--graphic-report", required=True, type=Path)
    parser.add_argument("--allow-changed", action="append", default=[])
    parser.add_argument("--allow-added", action="append", default=[])
    parser.add_argument("--verify-payloads", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    baseline = read_pack(args.baseline_pck.resolve())
    localized = read_pack(args.localized_pck.resolve())
    translations = load_string_map(args.translations)
    layout_overrides = load_layout_overrides(args.layout_overrides)
    manifest_counts, expected_changed, expected_added = (
        load_resource_manifest(args.resource_manifest)
    )
    expected_changed.update(load_graphic_report(args.graphic_report))
    expected_changed.update(args.allow_changed)
    expected_added.update(args.allow_added)

    baseline_paths = set(baseline.entries)
    localized_paths = set(localized.entries)
    actual_added = localized_paths - baseline_paths
    actual_removed = baseline_paths - localized_paths
    actual_changed = {
        path
        for path in baseline_paths & localized_paths
        if (
            baseline.entries[path].size,
            baseline.entries[path].digest,
            baseline.entries[path].flags,
        )
        != (
            localized.entries[path].size,
            localized.entries[path].digest,
            localized.entries[path].flags,
        )
    }

    errors: list[str] = []
    if actual_removed:
        errors.append(
            "localized PCK removed entries:" + format_paths(actual_removed)
        )
    if actual_added != expected_added:
        errors.append(
            "added PCK entries differ from the allowlist:"
            f"\n expected:{format_paths(expected_added)}"
            f"\n actual:{format_paths(actual_added)}"
        )
    if actual_changed != expected_changed:
        errors.append(
            "changed PCK entries differ from the allowlist:"
            f"\n unexpected:{format_paths(actual_changed - expected_changed)}"
            f"\n missing:{format_paths(expected_changed - actual_changed)}"
        )

    replayed_files = 0
    replayed_replacements = 0
    for resource_path, expected_count in manifest_counts.items():
        if resource_path in {
            "project.godot",
            "Asset/Translate/Translate.en.translation",
        }:
            continue
        baseline_entry = baseline.entries.get(resource_path)
        localized_entry = localized.entries.get(resource_path)
        if baseline_entry is None or localized_entry is None:
            errors.append(f"manifest resource is missing: {resource_path}")
            continue
        try:
            original_text = (
                read_payload(baseline, baseline_entry)
                .decode("utf-8-sig")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
            )
            localized_bytes = read_payload(localized, localized_entry)
            expected_text, count = replace_quoted_strings(
                original_text,
                translations,
            )
            if resource_path.endswith(".tscn"):
                expected_text, _ = apply_layout_overrides(
                    expected_text,
                    resource_path,
                    layout_overrides,
                )
        except (UnicodeDecodeError, ValueError) as error:
            errors.append(f"{resource_path}: {error}")
            continue
        expected_bytes = expected_text.encode("utf-8")
        if expected_bytes != localized_bytes:
            errors.append(
                "localized resource is not the exact declared string transform: "
                f"{resource_path}"
            )
        if count != expected_count:
            errors.append(
                f"replacement count changed for {resource_path}: "
                f"manifest={expected_count}, replay={count}"
            )
        if resource_path.endswith(".tscn"):
            try:
                verify_tscn_structure(
                    original_text,
                    localized_bytes.decode("utf-8"),
                    translations,
                    resource_path,
                )
            except (UnicodeDecodeError, ValueError) as error:
                errors.append(str(error))
        replayed_files += 1
        replayed_replacements += count

    if args.verify_payloads and not errors:
        verify_payloads(baseline)
        verify_payloads(localized)

    result = {
        "baseline_pck": str(baseline.path),
        "localized_pck": str(localized.path),
        "baseline_entries": len(baseline.entries),
        "localized_entries": len(localized.entries),
        "changed_entries": len(actual_changed),
        "added_entries": len(actual_added),
        "removed_entries": len(actual_removed),
        "expected_changed_entries": len(expected_changed),
        "expected_added_entries": len(expected_added),
        "replayed_text_files": replayed_files,
        "replayed_string_replacements": replayed_replacements,
        "payload_md5_verified": bool(args.verify_payloads and not errors),
        "status": "passed" if not errors else "failed",
        "errors": errors,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
