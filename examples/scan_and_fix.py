"""Damage a few clean sentences, scan them, and write a repaired copy.

Run: python examples/scan_and_fix.py
"""

import json
import tempfile
from pathlib import Path

from textdamage.fixer import fix_file
from textdamage.mojibake import make_mojibake
from textdamage.scan import scan_file

clean = [
    "café crème brûlée",
    "привет, мир",
    "Straße “quoted”",
    "plain ascii line",
]
rows = [
    {"id": "item-1", "source": "a", "text": make_mojibake(clean[0])},
    {"id": "item-2", "source": "a", "text": make_mojibake(clean[1], rounds=2)},
    {"id": "item-3", "source": "b", "text": clean[2]},
    {"id": "item-4", "source": "b", "text": clean[3] + "​"},
]

with tempfile.TemporaryDirectory() as tmp:
    src = Path(tmp) / "in.jsonl"
    src.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    report = scan_file(src, source_field="source").to_dict()
    for cls, st in report["classes"].items():
        print(f"{cls:12s} records={st['records']} occurrences={st['occurrences']}")
    out = Path(tmp) / "out.jsonl"
    res = fix_file(src, out, repairs=["mojibake", "invisible"])
    print(res.to_dict())
    for line in out.read_text(encoding="utf-8").splitlines():
        print(json.loads(line)["text"] in clean)
