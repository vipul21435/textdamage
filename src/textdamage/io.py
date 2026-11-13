"""Readers for JSON lines, JSON arrays, CSV/TSV and plain text, optionally gzip-compressed.

Every record keeps the exact bytes it was read from (``raw``), so ``fix`` can write undamaged records back
byte for byte.  Input is decoded as UTF-8 with ``surrogateescape``: bytes that are not valid UTF-8 become lone
surrogates U+DC80..U+DCFF (counted by the ``surrogate`` detector) and are written back unchanged.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


@dataclass
class Record:
    rid: str
    fields: list[tuple[str, str]]  # (field path, value)
    source: str | None
    raw: bytes
    obj: Any = None
    line: int = 0
    passthrough: bool = False  # blank, malformed or header rows: not scanned, written back unchanged by fix


@dataclass
class InputErrors:
    items: list[tuple[int, str]] = field(default_factory=list)

    def add(self, line: int, message: str) -> None:
        self.items.append((line, message))


def detect_format(path: str | Path) -> str:
    name = str(path).lower()
    if name.endswith(".gz"):
        name = name[:-3]
    if name.endswith((".jsonl", ".ndjson")):
        return "jsonl"
    if name.endswith(".json"):
        return "json"
    if name.endswith(".csv"):
        return "csv"
    if name.endswith(".tsv"):
        return "tsv"
    return "txt"


def read_bytes(path: str | Path) -> bytes:
    data = Path(path).read_bytes()
    if str(path).lower().endswith(".gz"):
        data = gzip.decompress(data)
    return data


def decode(data: bytes) -> str:
    return data.decode("utf-8", errors="surrogateescape")


def encode(text: str) -> bytes:
    return text.encode("utf-8", errors="surrogateescape")


def walk_strings(obj: Any, prefix: str = "") -> Iterator[tuple[str, str]]:
    """Every string inside a JSON value, with a path like ``messages[].content`` (list indices collapsed)."""
    if isinstance(obj, str):
        yield prefix, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v, f"{prefix}[]")


def _lookup(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _source_value(value: Any, host: bool) -> str | None:
    if value is None:
        return None
    s = str(value)
    if host:
        s = urlsplit(s).hostname or s
    return s


def _select(pairs: list[tuple[str, str]], fields: list[str] | None) -> list[tuple[str, str]]:
    if not fields:
        return pairs
    return [(p, v) for p, v in pairs if p in fields]


def iter_records(
    path: str | Path,
    *,
    fields: list[str] | None = None,
    id_field: str | None = None,
    source_field: str | None = None,
    source_host: bool = False,
    fmt: str | None = None,
    errors: InputErrors | None = None,
) -> Iterator[Record]:
    """Yield records from ``path``.  Malformed rows are reported to ``errors`` and skipped."""
    fmt = fmt or detect_format(path)
    errors = errors if errors is not None else InputErrors()
    data = read_bytes(path)
    if fmt == "jsonl":
        yield from _jsonl(data, fields, id_field, source_field, source_host, errors)
    elif fmt == "json":
        yield from _json(data, fields, id_field, source_field, source_host, errors)
    elif fmt in ("csv", "tsv"):
        yield from _csv(data, "\t" if fmt == "tsv" else ",", fields, id_field, source_field, source_host, errors)
    elif fmt == "txt":
        for n, raw in enumerate(data.splitlines(keepends=True), 1):
            text = decode(raw).rstrip("\r\n")
            if n == 1:
                text = text.removeprefix("﻿")
            yield Record(str(n), [("text", text)], None, raw, None, n)
    else:
        raise ValueError(f"unknown format: {fmt}")


def _record_from_obj(obj, n, raw, fields, id_field, source_field, source_host) -> Record:
    rid = None
    if isinstance(obj, dict):
        key = id_field or ("id" if "id" in obj else None)
        if key is not None:
            v = _lookup(obj, key)
            rid = None if v is None else str(v)
    src = _source_value(_lookup(obj, source_field), source_host) if source_field and isinstance(obj, dict) else None
    return Record(rid or str(n), _select(list(walk_strings(obj)), fields), src, raw, obj, n)


def _jsonl(data, fields, id_field, source_field, source_host, errors) -> Iterator[Record]:
    for n, raw in enumerate(data.splitlines(keepends=True), 1):
        text = decode(raw)
        if n == 1:
            text = text.removeprefix("﻿")
        if not text.strip():
            yield Record("", [], None, raw, None, n, passthrough=True)
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            errors.add(n, f"invalid JSON: {exc.msg}")
            yield Record("", [], None, raw, None, n, passthrough=True)
            continue
        yield _record_from_obj(obj, n, raw, fields, id_field, source_field, source_host)


def _json(data, fields, id_field, source_field, source_host, errors) -> Iterator[Record]:
    text = decode(data).removeprefix("﻿")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.add(exc.lineno, f"invalid JSON: {exc.msg}")
        return
    items = obj if isinstance(obj, list) else [obj]
    for n, item in enumerate(items, 1):
        yield _record_from_obj(item, n, b"", fields, id_field, source_field, source_host)


class _LineTap:
    """Feeds lines to ``csv.reader`` and remembers which lines each row consumed."""

    def __init__(self, text: str):
        self._lines = iter(io.StringIO(text, newline="").readlines())
        self.consumed: list[str] = []

    def __iter__(self):
        return self

    def __next__(self) -> str:
        line = next(self._lines)
        self.consumed.append(line)
        return line


def _csv(data, delim, fields, id_field, source_field, source_host, errors) -> Iterator[Record]:
    text = decode(data)
    bom = text.startswith("﻿")
    tap = _LineTap(text[1:] if bom else text)
    reader = csv.reader(tap, delimiter=delim)
    try:
        header = next(reader)
    except StopIteration:
        return
    except csv.Error as exc:
        errors.add(1, f"invalid CSV header: {exc}")
        return
    header_raw = ("﻿" if bom else "") + "".join(tap.consumed)
    yield Record("", [], None, encode(header_raw), header, 0, passthrough=True)
    tap.consumed = []
    row_no = 0
    while True:
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            errors.add(reader.line_num, f"invalid CSV: {exc}")
            yield Record("", [], None, encode("".join(tap.consumed)), None, reader.line_num, passthrough=True)
            tap.consumed = []
            continue
        raw = encode("".join(tap.consumed))
        tap.consumed = []
        row_no += 1
        if len(row) != len(header):
            errors.add(reader.line_num, f"expected {len(header)} columns, got {len(row)}")
            yield Record(str(row_no), [], None, raw, None, row_no, passthrough=True)
            continue
        obj = dict(zip(header, row, strict=True))
        key = id_field or ("id" if "id" in obj else None)
        rid = obj.get(key) if key else None
        src = _source_value(obj.get(source_field), source_host) if source_field else None
        pairs = [(k, v) for k, v in obj.items() if k not in (key, source_field)]
        yield Record(rid or str(row_no), _select(pairs, fields), src, raw, row, row_no)
