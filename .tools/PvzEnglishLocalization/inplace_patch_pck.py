#!/usr/bin/env python3
"""Patch a Godot PCK v2/v4 directory in place with a small rollback journal.

Godot RE Tools normally writes a complete second PCK. This helper is intended
for large packs on space-constrained APFS volumes: replacement payloads are
written where the old directory started, then a rebuilt directory is appended.
The original directory and header are journaled first so an interrupted write
can be rolled back without duplicating the full pack.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import struct
import sys
from typing import BinaryIO


PCK_MAGIC = b"GDPC"
HEADER_SIZE = 112
DIRECTORY_OFFSET_FIELD = 32
ALIGNMENT = 16


@dataclass
class Entry:
    path_raw: bytes
    path: str
    offset: int
    size: int
    digest: bytes
    flags: int


def read_exact(handle: BinaryIO, size: int) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise ValueError(f"unexpected EOF: wanted {size} bytes, got {len(data)}")
    return data


def unpack_u32(data: bytes) -> int:
    return struct.unpack("<I", data)[0]


def unpack_u64(data: bytes) -> int:
    return struct.unpack("<Q", data)[0]


def align(value: int, alignment: int = ALIGNMENT) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def normalize_pack_path(value: str) -> str:
    value = value.replace("\\", "/")
    if value.startswith("res://"):
        value = value[6:]
    return value.lstrip("/")


def parse_header(handle: BinaryIO, file_size: int) -> tuple[bytearray, int, int]:
    handle.seek(0)
    header = bytearray(read_exact(handle, HEADER_SIZE))
    if header[:4] != PCK_MAGIC:
        raise ValueError("not a standalone Godot PCK (missing GDPC header)")
    pack_format = unpack_u32(header[4:8])
    if pack_format not in (2, 3, 4):
        raise ValueError(f"unsupported PCK format: {pack_format}")
    file_base = unpack_u64(header[24:32])
    directory_offset = unpack_u64(header[32:40])
    if not (HEADER_SIZE <= file_base <= directory_offset < file_size):
        raise ValueError(
            "invalid PCK offsets: "
            f"file_base={file_base}, directory_offset={directory_offset}, "
            f"file_size={file_size}"
        )
    return header, file_base, directory_offset


def parse_directory(
    handle: BinaryIO, directory_offset: int, file_size: int
) -> tuple[list[Entry], bytes, bytes]:
    handle.seek(directory_offset)
    directory_blob = read_exact(handle, file_size - directory_offset)
    cursor = 0
    if len(directory_blob) < 4:
        raise ValueError("truncated PCK directory")
    count = unpack_u32(directory_blob[cursor : cursor + 4])
    cursor += 4
    if count > 10_000_000:
        raise ValueError(f"implausible PCK entry count: {count}")

    entries: list[Entry] = []
    for index in range(count):
        if cursor + 4 > len(directory_blob):
            raise ValueError(f"truncated directory before entry {index}")
        path_size = unpack_u32(directory_blob[cursor : cursor + 4])
        cursor += 4
        if path_size == 0 or path_size > 1_048_576 or cursor + path_size > len(
            directory_blob
        ):
            raise ValueError(f"invalid path size for entry {index}: {path_size}")
        path_raw = directory_blob[cursor : cursor + path_size]
        cursor += path_size
        if cursor + 36 > len(directory_blob):
            raise ValueError(f"truncated metadata for entry {index}")
        offset = unpack_u64(directory_blob[cursor : cursor + 8])
        size = unpack_u64(directory_blob[cursor + 8 : cursor + 16])
        digest = directory_blob[cursor + 16 : cursor + 32]
        flags = unpack_u32(directory_blob[cursor + 32 : cursor + 36])
        cursor += 36
        path = path_raw.rstrip(b"\0").decode("utf-8")
        entries.append(Entry(path_raw, path, offset, size, digest, flags))

    trailer = directory_blob[cursor:]
    valid_trailers = (b"", b"\0" * 12 + PCK_MAGIC)
    if trailer not in valid_trailers:
        raise ValueError(f"unexpected PCK directory trailer ({len(trailer)} bytes)")
    return entries, directory_blob, trailer


def build_directory(entries: list[Entry], trailer: bytes) -> bytes:
    output = bytearray(struct.pack("<I", len(entries)))
    for entry in entries:
        output.extend(struct.pack("<I", len(entry.path_raw)))
        output.extend(entry.path_raw)
        output.extend(struct.pack("<Q", entry.offset))
        output.extend(struct.pack("<Q", entry.size))
        if len(entry.digest) != 16:
            raise ValueError(f"invalid MD5 length for {entry.path}")
        output.extend(entry.digest)
        output.extend(struct.pack("<I", entry.flags))
    output.extend(trailer)
    return bytes(output)


def parse_patch(value: str) -> tuple[Path, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected SOURCE=DESTINATION")
    source_text, destination = value.split("=", 1)
    source = Path(source_text).expanduser().resolve()
    if not source.is_file():
        raise argparse.ArgumentTypeError(f"patch source is not a file: {source}")
    destination = normalize_pack_path(destination)
    if not destination:
        raise argparse.ArgumentTypeError("empty pack destination")
    return source, destination


def restore(
    pck_path: Path,
    original_header: bytes,
    original_directory: bytes,
    original_directory_offset: int,
    original_size: int,
) -> None:
    with pck_path.open("r+b", buffering=0) as handle:
        handle.seek(original_directory_offset)
        handle.write(original_directory)
        handle.truncate(original_size)
        handle.seek(0)
        handle.write(original_header)
        handle.flush()
        os.fsync(handle.fileno())


def padded_path(value: str) -> bytes:
    encoded = value.encode("utf-8")
    size = align(len(encoded), 4)
    return encoded + b"\0" * (size - len(encoded))


def patch_pck(
    pck_path: Path,
    patches: list[tuple[Path, str]],
    additions: list[tuple[Path, str]],
) -> dict[str, object]:
    original_size = pck_path.stat().st_size
    journal_path = pck_path.with_name(pck_path.name + ".directory-journal")
    if journal_path.exists():
        raise ValueError(
            f"rollback journal already exists; inspect or remove it first: {journal_path}"
        )

    with pck_path.open("rb") as handle:
        header, file_base, directory_offset = parse_header(handle, original_size)
        entries, original_directory, directory_trailer = parse_directory(
            handle, directory_offset, original_size
        )

    by_path = {entry.path: entry for entry in entries}
    if len(by_path) != len(entries):
        raise ValueError("PCK contains duplicate directory paths")

    destinations: set[str] = set()
    resolved: list[tuple[Path, Entry, bool]] = []
    for source, destination in patches:
        if destination in destinations:
            raise ValueError(f"duplicate patch destination: {destination}")
        destinations.add(destination)
        entry = by_path.get(destination)
        if entry is None:
            raise ValueError(f"destination not found in PCK: {destination}")
        resolved.append((source, entry, False))
    for source, destination in additions:
        if destination in destinations:
            raise ValueError(f"duplicate patch destination: {destination}")
        destinations.add(destination)
        if destination in by_path:
            raise ValueError(
                f"added destination already exists in PCK: {destination}"
            )
        entry = Entry(
            path_raw=padded_path(destination),
            path=destination,
            offset=0,
            size=0,
            digest=b"\0" * 16,
            flags=0,
        )
        entries.append(entry)
        by_path[destination] = entry
        resolved.append((source, entry, True))

    journal = {
        "pck": str(pck_path),
        "original_size": original_size,
        "directory_offset": directory_offset,
        "header_hex": bytes(header).hex(),
        "directory_hex": original_directory.hex(),
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    with journal_path.open("rb") as journal_handle:
        os.fsync(journal_handle.fileno())

    patched_records: list[dict[str, object]] = []
    try:
        with pck_path.open("r+b", buffering=0) as handle:
            cursor = directory_offset
            for source, entry, was_added in resolved:
                cursor = align(cursor)
                handle.seek(cursor)
                digest = hashlib.md5()
                written = 0
                with source.open("rb") as source_handle:
                    while chunk := source_handle.read(1024 * 1024):
                        handle.write(chunk)
                        digest.update(chunk)
                        written += len(chunk)
                entry.offset = cursor - file_base
                entry.size = written
                entry.digest = digest.digest()
                patched_records.append(
                    {
                        "path": entry.path,
                        "source": str(source),
                        "size": written,
                        "md5": digest.hexdigest(),
                        "absolute_offset": cursor,
                        "added": was_added,
                    }
                )
                cursor += written

            new_directory_offset = align(cursor)
            handle.seek(new_directory_offset)
            new_directory = build_directory(entries, directory_trailer)
            handle.write(new_directory)
            new_size = new_directory_offset + len(new_directory)
            handle.truncate(new_size)
            struct.pack_into("<Q", header, DIRECTORY_OFFSET_FIELD, new_directory_offset)
            handle.seek(0)
            handle.write(header)
            handle.flush()
            os.fsync(handle.fileno())

        with pck_path.open("rb") as handle:
            check_header, check_file_base, check_directory_offset = parse_header(
                handle, pck_path.stat().st_size
            )
            check_entries, _, _ = parse_directory(
                handle, check_directory_offset, pck_path.stat().st_size
            )
            check_by_path = {entry.path: entry for entry in check_entries}
            if check_file_base != file_base:
                raise ValueError("file base changed unexpectedly")
            for record in patched_records:
                entry = check_by_path[str(record["path"])]
                handle.seek(file_base + entry.offset)
                digest = hashlib.md5()
                remaining = entry.size
                while remaining:
                    chunk = read_exact(handle, min(1024 * 1024, remaining))
                    digest.update(chunk)
                    remaining -= len(chunk)
                if digest.hexdigest() != record["md5"]:
                    raise ValueError(f"post-write checksum mismatch: {entry.path}")
    except BaseException:
        restore(
            pck_path,
            bytes.fromhex(journal["header_hex"]),
            bytes.fromhex(journal["directory_hex"]),
            original_directory_offset=directory_offset,
            original_size=original_size,
        )
        raise
    else:
        journal_path.unlink()

    return {
        "pck": str(pck_path),
        "format": unpack_u32(check_header[4:8]),
        "entry_count": len(check_entries),
        "patched_count": len(patched_records),
        "original_size": original_size,
        "new_size": pck_path.stat().st_size,
        "new_directory_offset": check_directory_offset,
        "patched": patched_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pck", required=True, type=Path)
    parser.add_argument(
        "--patch-root",
        type=Path,
        help=(
            "Patch every file below this root at its relative PCK path; "
            "new paths are added automatically."
        ),
    )
    parser.add_argument(
        "--patch-file",
        action="append",
        default=[],
        type=parse_patch,
        metavar="SOURCE=DESTINATION",
    )
    parser.add_argument(
        "--add-file",
        action="append",
        default=[],
        type=parse_patch,
        metavar="SOURCE=DESTINATION",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    pck_path = args.pck.expanduser().resolve()
    if not pck_path.is_file():
        parser.error(f"PCK is not a file: {pck_path}")
    patch_files = list(args.patch_file)
    add_files = list(args.add_file)
    if args.patch_root:
        patch_root = args.patch_root.expanduser().resolve()
        if not patch_root.is_dir():
            parser.error(f"patch root is not a directory: {patch_root}")
        with pck_path.open("rb") as handle:
            _, _, directory_offset = parse_header(
                handle,
                pck_path.stat().st_size,
            )
            entries, _, _ = parse_directory(
                handle,
                directory_offset,
                pck_path.stat().st_size,
            )
        existing_paths = {entry.path for entry in entries}
        for source in sorted(patch_root.rglob("*")):
            if not source.is_file():
                continue
            destination = source.relative_to(patch_root).as_posix()
            pair = (source.resolve(), destination)
            if destination in existing_paths:
                patch_files.append(pair)
            else:
                add_files.append(pair)
    if not patch_files and not add_files:
        parser.error("at least one --patch-file or --add-file is required")

    try:
        report = patch_pck(pck_path, patch_files, add_files)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    report_text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report_text + "\n", encoding="utf-8")
    print(report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
