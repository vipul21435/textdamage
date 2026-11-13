"""Put several ``textdamage scan --json`` reports side by side as one Markdown table.

Usage: python scripts/table.py NAME=report.json [NAME=report.json ...]

Rows are damage classes, columns are datasets; each cell is the share of records with that class and, in
brackets, the number of records.
"""

from __future__ import annotations

import json
import sys

from textdamage.detectors import CLASSES


def main(argv: list[str]) -> int:
    reports = []
    for arg in argv[1:]:
        name, path = arg.split("=", 1)
        with open(path, encoding="utf-8") as fh:
            reports.append((name, json.load(fh)))
    head = "| class | " + " | ".join(n for n, _ in reports) + " |"
    lines = [head, "|---|" + "---|" * len(reports)]
    lines.append("| records scanned | " + " | ".join(f"{d['records']:,}" for _, d in reports) + " |")
    lines.append(
        "| any damage | "
        + " | ".join(f"{d['damaged_records'] / d['records']:.2%} ({d['damaged_records']:,})" for _, d in reports)
        + " |"
    )
    for cls in CLASSES:
        if not any(cls in d["classes"] for _, d in reports):
            continue
        cells = []
        for _, d in reports:
            st = d["classes"].get(cls)
            cells.append("0" if st is None else f"{st['share']:.2%} ({st['records']:,})")
        lines.append(f"| {cls} | " + " | ".join(cells) + " |")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
