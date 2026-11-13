"""Command line interface: ``textdamage scan | explain | fix | sources``."""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

from . import __version__
from .chars import display, script_of
from .detectors import CLASSES, scan_text


def _parse_char(spec: str) -> set[str]:
    """``U+200D``, ``U+FE00..U+FE0F``, ``200d`` or a literal character."""
    spec = spec.strip()
    if ".." in spec:
        lo, hi = (int(p.upper().removeprefix("U+"), 16) for p in spec.split("..", 1))
        return {chr(c) for c in range(lo, hi + 1)}
    if spec.upper().startswith("U+"):
        return {chr(int(spec[2:], 16))}
    if len(spec) > 1 and all(c in "0123456789abcdefABCDEF" for c in spec):
        return {chr(int(spec, 16))}
    return set(spec)


def _ignore_set(args) -> set[str]:
    out: set[str] = set()
    for spec in args.ignore or []:
        out |= _parse_char(spec)
    if args.ignore_file:
        for line in Path(args.ignore_file).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                out |= _parse_char(line)
    return out


def _classes(args) -> list[str] | None:
    if not args.classes:
        return None
    out = [c.strip() for c in args.classes.split(",") if c.strip()]
    bad = [c for c in out if c not in CLASSES]
    if bad:
        raise SystemExit(f"textdamage: unknown class {bad[0]!r}; known: {', '.join(CLASSES)}")
    return out


def _add_input_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("path", help="JSON lines, JSON array, CSV/TSV or text file (optionally .gz)")
    p.add_argument("--field", action="append", dest="fields", help="text field to scan (repeatable; "
                   "nested paths like messages[].content); default every string field")
    p.add_argument("--id-field", help="field holding the record id (default 'id' when present, else line number)")
    p.add_argument("--source-field", help="field naming the record's source or group")
    p.add_argument("--source-host", action="store_true", help="reduce a URL source to its host name")
    p.add_argument("--format", dest="fmt", choices=["jsonl", "json", "csv", "tsv", "txt"],
                   help="input format (default from the file name)")
    p.add_argument("--repeat-min", type=int, default=10, help="shortest run counted as a repeat (default 10)")
    p.add_argument("--ignore", action="append", help="character a project accepts: U+200D, U+FE00..U+FE0F")
    p.add_argument("--ignore-file", help="file with one --ignore entry per line")
    p.add_argument("--classes", help="comma-separated classes to run (default all)")
    p.add_argument("--limit", type=int, help="scan only the first N records")


def _write(text: str, out: str | None) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def cmd_scan(args) -> int:
    from .scan import scan_file

    report = scan_file(
        args.path, fields=args.fields, id_field=args.id_field, source_field=args.source_field,
        source_host=args.source_host, fmt=args.fmt, repeat_min=args.repeat_min, ignore=_ignore_set(args),
        classes=_classes(args), limit=args.limit, top_sources=args.top_sources,
    )
    _write(report.to_json() + "\n" if args.json else report.to_markdown(f"textdamage scan: {Path(args.path).name}"),
           args.output)
    return 0


def explain_rows(text: str) -> list[dict]:
    findings = scan_text(text)
    rows = []
    for i, ch in enumerate(text):
        try:
            name = unicodedata.name(ch)
        except ValueError:
            name = ""
        rows.append({
            "index": i,
            "char": display(ch),
            "codepoint": f"U+{ord(ch):04X}",
            "name": name,
            "category": unicodedata.category(ch),
            "script": script_of(ch) if unicodedata.category(ch)[0] in "LM" else "",
            "classes": sorted({f.cls for f in findings if f.start <= i < f.end}),
        })
    return rows


def cmd_explain(args) -> int:
    text = args.text
    if args.unescape:
        text = text.encode("latin-1", "backslashreplace").decode("unicode_escape")
    findings = scan_text(text)
    rows = explain_rows(text)
    if args.json:
        out = {
            "text": text,
            "characters": rows,
            "findings": [{"class": f.cls, "start": f.start, "end": f.end, "text": f.text, "fix": f.fix}
                         for f in findings],
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        return 0
    lines = ["| # | char | code point | name | category | script | classes |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['index']} | {r['char']} | {r['codepoint']} | {r['name']} | {r['category']} | "
                     f"{r['script']} | {', '.join(r['classes'])} |")
    lines.append("")
    if not findings:
        lines.append("No damage found.")
    for f in findings:
        fix = f" -> {display(f.fix)!r}" if f.fix is not None and f.cls.startswith("mojibake") else ""
        lines.append(f"- {f.cls} at {f.start}..{f.end}: {display(f.text)!r}{fix}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="textdamage", description=__doc__)
    p.add_argument("--version", action="version", version=f"textdamage {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="count damage per class, field and source")
    _add_input_args(s)
    s.add_argument("--top-sources", type=int, default=3, help="k for the share of damage in the top k sources")
    s.add_argument("--json", action="store_true", help="JSON instead of Markdown")
    s.add_argument("-o", "--output", help="write the report here instead of stdout")
    s.set_defaults(func=cmd_scan)

    e = sub.add_parser("explain", help="show one string character by character")
    e.add_argument("text")
    e.add_argument("-e", "--unescape", action="store_true", help="read \\uXXXX and \\xXX escapes in TEXT")
    e.add_argument("--json", action="store_true")
    e.set_defaults(func=cmd_explain)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"textdamage: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
