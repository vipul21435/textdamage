"""Writing a repaired copy of a file.

Only classes whose repair does not need a guess are offered:

- ``mojibake``: accepted mojibake hits (one or two rounds) are decoded; ambiguous hits are left alone;
- ``bom``: U+FEFF inside a value is deleted;
- ``c0``: C0 controls other than tab, LF and CR, and DEL, are deleted;
- ``c1``: C1 controls left after the mojibake repair are deleted;
- ``invisible``: soft hyphen, zero width space, word joiner, invisible operators, the Mongolian vowel
  separator and the deprecated format characters are deleted (joiners, variation selectors, tags and fillers
  are kept: they can carry meaning);
- ``non-nfc``: values are normalised to NFC (canonically equivalent, so the text means the same).

The change log is JSON lines with ASCII escapes, so invisible characters stay visible in it.  Records with no
change are written back as the exact bytes they were read from; a changed record is
re-serialised (JSON lines with ``ensure_ascii=False``, CSV rows with the csv module).  After writing, the
output is read back and every unchanged record is compared byte for byte with the input.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import chars
from .io import InputErrors, detect_format, encode, iter_records
from .mojibake import find_mojibake

REPAIRABLE: tuple[str, ...] = ("mojibake", "bom", "c0", "c1", "invisible", "non-nfc")
DEFAULT_REPAIRS: tuple[str, ...] = ("mojibake",)


@dataclass(frozen=True)
class Change:
    cls: str
    before: str
    after: str


def repair_text(text: str, repairs: Iterable[str], ignore: frozenset[str] = frozenset()) -> tuple[str, list[Change]]:
    """Apply the chosen repairs to one string.  Returns the new string and the list of changes."""
    want = set(repairs)
    bad = want - set(REPAIRABLE)
    if bad:
        raise ValueError(f"not a repairable class: {sorted(bad)[0]}; choose from {', '.join(REPAIRABLE)}")
    changes: list[Change] = []
    if "mojibake" in want:
        parts, pos = [], 0
        for h in find_mojibake(text):
            if h.fix is None:
                continue
            parts += [text[pos : h.start], h.fix]
            changes.append(Change("mojibake-2" if h.rounds == 2 else "mojibake", h.text, h.fix))
            pos = h.end
        parts.append(text[pos:])
        text = "".join(parts)
    deletions = [
        ("bom", frozenset(chars.BOM)),
        ("c0", chars.C0),
        ("c1", chars.C1),
        ("invisible", chars.REMOVABLE_INVISIBLE),
    ]
    for cls, table in deletions:
        if cls in want and any(c in table for c in text):
            kept = []
            for c in text:
                if c in table and c not in ignore:
                    changes.append(Change(cls, c, ""))
                else:
                    kept.append(c)
            text = "".join(kept)
    if "non-nfc" in want and not unicodedata.is_normalized("NFC", text):
        new = unicodedata.normalize("NFC", text)
        changes.append(Change("non-nfc", text[:16], new[:16]))
        text = new
    return text, changes


def _map_strings(obj: Any, fn, prefix: str = "") -> Any:
    if isinstance(obj, str):
        return fn(prefix, obj)
    if isinstance(obj, dict):
        return {k: _map_strings(v, fn, f"{prefix}.{k}" if prefix else str(k)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_map_strings(v, fn, f"{prefix}[]") for v in obj]
    return obj


def _line_ending(raw: bytes) -> bytes:
    if raw.endswith(b"\r\n"):
        return b"\r\n"
    if raw.endswith(b"\n"):
        return b"\n"
    if raw.endswith(b"\r"):
        return b"\r"
    return b""


@dataclass
class FixResult:
    records: int = 0
    changed: int = 0
    unchanged_identical: int = 0
    mismatches: list[int] = field(default_factory=list)
    changes: Counter = field(default_factory=Counter)
    input_errors: list[tuple[int, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def to_dict(self) -> dict:
        return {
            "records": self.records,
            "changed_records": self.changed,
            "unchanged_records_byte_identical": self.unchanged_identical,
            "round_trip_mismatches": self.mismatches[:20],
            "changes": dict(self.changes.most_common()),
            "input_errors": len(self.input_errors),
        }


def _open_out(path: Path):
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, "wb")
    return open(path, "wb")


def fix_file(
    src: str | Path,
    out: str | Path,
    *,
    repairs: Iterable[str] = DEFAULT_REPAIRS,
    fields: list[str] | None = None,
    id_field: str | None = None,
    fmt: str | None = None,
    log: str | Path | None = None,
    ignore: Iterable[str] = (),
    force: bool = False,
) -> FixResult:
    """Write a repaired copy of ``src`` to ``out`` and a change log, then verify the round trip."""
    src, out = Path(src), Path(out)
    fmt = fmt or detect_format(src)
    if fmt not in ("jsonl", "csv", "tsv", "txt"):
        raise ValueError("fix supports JSON lines, CSV/TSV and text files (not JSON arrays)")
    if out.resolve() == src.resolve() or (out.exists() and src.exists() and out.samefile(src)):
        raise ValueError("fix never edits in place: choose a different output path")
    log = Path(log) if log else out.with_name(out.name + ".changes.jsonl")
    for p in (out, log):
        if p.exists() and not force:
            raise ValueError(f"{p} exists; pass --force to overwrite")
    repairs = tuple(repairs)
    ign = frozenset(ignore)
    want_fields = set(fields) if fields else None
    errors = InputErrors()
    result = FixResult()
    raws: list[bytes] = []
    changed_idx: set[int] = set()
    passthrough_idx: set[int] = set()
    header: list[str] = []
    delim = "\t" if fmt == "tsv" else ","
    with _open_out(out) as fo, open(log, "w", encoding="utf-8") as fl:
        for idx, rec in enumerate(iter_records(src, id_field=id_field, fmt=fmt, errors=errors)):
            raws.append(rec.raw)
            if rec.passthrough:
                passthrough_idx.add(idx)
                if fmt in ("csv", "tsv") and rec.line == 0 and isinstance(rec.obj, list):
                    header = list(rec.obj)
                fo.write(rec.raw)
                continue
            result.records += 1
            rec_changes: list[tuple[str, Change]] = []

            def fn(path: str, value: str, _acc=rec_changes) -> str:
                if want_fields is not None and path not in want_fields:
                    return value
                new, ch = repair_text(value, repairs, ign)
                _acc.extend((path, c) for c in ch)
                return new

            if fmt == "jsonl":
                new_obj = _map_strings(rec.obj, fn)
            elif fmt == "txt":
                new_obj = fn("text", rec.fields[0][1])
            else:
                new_obj = [fn(h, v) for h, v in zip(header, rec.obj, strict=True)]
            new_bytes = _serialise(fmt, new_obj, rec.raw, delim) if rec_changes else rec.raw
            if rec_changes and new_bytes.startswith(b"\n") and idx > 0 and raws[idx - 1].endswith(b"\r"):
                # a line emptied by the repair after a bare CR would join the two lines: keep it as it was
                rec_changes, new_bytes = [], rec.raw
            if not rec_changes:
                fo.write(rec.raw)
                continue
            result.changed += 1
            changed_idx.add(idx)
            fo.write(new_bytes)
            for path, c in rec_changes:
                result.changes[c.cls] += 1
                fl.write(json.dumps({"id": rec.rid, "line": rec.line, "field": path, "class": c.cls,
                                     "before": c.before, "after": c.after}, ensure_ascii=True) + "\n")
    result.input_errors = errors.items
    # round trip: read the output back and compare unchanged records byte for byte
    back = [r.raw for r in iter_records(out, fmt=fmt)]
    if len(back) != len(raws):
        result.mismatches.append(-1)
    for i, (a, b) in enumerate(zip(raws, back, strict=False)):
        if i in changed_idx:
            continue
        if a != b:
            result.mismatches.append(i)
        elif i not in passthrough_idx:
            result.unchanged_identical += 1
    return result


def _serialise(fmt: str, obj: Any, raw: bytes, delim: str) -> bytes:
    end = _line_ending(raw)
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    if fmt == "jsonl":
        text = json.dumps(obj, ensure_ascii=False)
        try:
            return bom + encode(text) + end
        except UnicodeEncodeError:  # lone surrogates outside the surrogateescape range
            return bom + json.dumps(obj).encode("ascii") + end
    if fmt == "txt":
        return bom + encode(obj) + end
    buf = io.StringIO()
    csv.writer(buf, delimiter=delim, lineterminator=end.decode() or "\n").writerow(obj)
    return encode(buf.getvalue())
