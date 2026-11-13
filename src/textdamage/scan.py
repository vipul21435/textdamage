"""Scanning a file into a report."""

from __future__ import annotations

import random
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
    sample: int | None = None,
    seed: int = 0,
    top_sources: int = 3,
) -> Report:
    """Scan every selected text field of every record in ``path``.

    ``limit`` stops after the first N records; ``sample`` scans a uniform random sample of N records
    (reservoir sampling with ``seed``), in file order.
    """
    errors = InputErrors()
    report = Report(top_sources=top_sources)
    ign = frozenset(ignore)
    cls = None if classes is None else list(classes)
    records = (
        r
        for r in iter_records(
            path, fields=fields, id_field=id_field, source_field=source_field, source_host=source_host,
            fmt=fmt, errors=errors,
        )
        if not r.passthrough
    )
    if sample is not None:
        records = iter(reservoir(records, sample, seed))
    for rec in records:
        if limit is not None and report.records >= limit:
            break
        found = []
        for fname, value in rec.fields:
            found += [(fname, f) for f in scan_text(value, repeat_min=repeat_min, ignore=ign, classes=cls)]
        report.add(rec.rid, rec.source, found, [f for f, _ in rec.fields])
    report.input_errors = errors.items
    return report


def reservoir(items, k: int, seed: int = 0) -> list:
    """Uniform sample of ``k`` items (Algorithm R), returned in input order."""
    if k < 0:
        raise ValueError("sample size must be non-negative")
    rng = random.Random(seed)
    kept: list = []
    for i, item in enumerate(items):
        if i < k:
            kept.append((i, item))
        else:
            j = rng.randint(0, i)
            if j < k:
                kept[j] = (i, item)
    kept.sort(key=lambda t: t[0])
    return [item for _, item in kept]
