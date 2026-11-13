"""Scanning a file into a report."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .detectors import scan_text
from .io import InputErrors, iter_records
from .report import Report


def scan_file(
    path: str | Path,
    *,
    fields: list[str] | None = None,
    id_field: str | None = None,
    source_field: str | None = None,
    source_host: bool = False,
    fmt: str | None = None,
    repeat_min: int = 10,
    ignore: Iterable[str] = (),
    classes: Iterable[str] | None = None,
    limit: int | None = None,
    top_sources: int = 3,
) -> Report:
    """Scan every selected text field of every record in ``path``."""
    errors = InputErrors()
    report = Report(top_sources=top_sources)
    ign = frozenset(ignore)
    cls = None if classes is None else list(classes)
    for rec in iter_records(
        path, fields=fields, id_field=id_field, source_field=source_field, source_host=source_host,
        fmt=fmt, errors=errors,
    ):
        if rec.passthrough:
            continue
        if limit is not None and report.records >= limit:
            break
        found = []
        for fname, value in rec.fields:
            found += [(fname, f) for f in scan_text(value, repeat_min=repeat_min, ignore=ign, classes=cls)]
        report.add(rec.rid, rec.source, found, [f for f, _ in rec.fields])
    report.input_errors = errors.items
    return report
