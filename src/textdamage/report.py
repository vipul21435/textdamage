"""Aggregation of findings per class, field and source, and Markdown/JSON rendering."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from .chars import display
from .detectors import CLASSES, Finding

MAX_SEQ = 8  # longest damaged sequence shown in a report


@dataclass
class _Stats:
    records: set = field(default_factory=set)
    occurrences: int = 0
    sequences: Counter = field(default_factory=Counter)
    examples: list = field(default_factory=list)


class Report:
    """Collects findings record by record."""

    def __init__(self, *, examples: int = 3, top_sequences: int = 5, top_sources: int = 3):
        self.n_examples = examples
        self.n_sequences = top_sequences
        self.n_top_sources = top_sources
        self.records = 0
        self.damaged: set[str] = set()
        self.by_class: dict[str, _Stats] = defaultdict(_Stats)
        self.by_field: dict[str, dict[str, _Stats]] = defaultdict(lambda: defaultdict(_Stats))
        self.field_records: Counter = Counter()
        self.source_records: Counter = Counter()
        self.by_source: dict[str, Counter] = defaultdict(Counter)
        self.source_damaged: dict[str, set] = defaultdict(set)
        self.source_examples: dict[str, list] = defaultdict(list)
        self.input_errors: list[tuple[int, str]] = []
        self.repairs: Counter = Counter()  # (class, damaged text, proposed repair) -> count

    def add(self, rid: str, source: str | None, findings: Iterable[tuple[str, Finding]], fields: Iterable[str]):
        self.records += 1
        key = f"{rid}\x00{self.records}"
        for f in set(fields):
            self.field_records[f] += 1
        if source is not None:
            self.source_records[source] += 1
        for fname, fd in findings:
            self.damaged.add(key)
            if fd.fix is not None and fd.cls in ("mojibake", "mojibake-2"):
                self.repairs[(fd.cls, fd.text[:MAX_SEQ], fd.fix[:MAX_SEQ])] += 1
            for st in (self.by_class[fd.cls], self.by_field[fname][fd.cls]):
                st.records.add(key)
                st.occurrences += 1
                st.sequences[fd.text[:MAX_SEQ]] += 1
                if len(st.examples) < self.n_examples and rid not in st.examples:
                    st.examples.append(rid)
            if source is not None:
                self.by_source[source][fd.cls] += 1
                self.source_damaged[source].add(key)
                ex = self.source_examples[source]
                if len(ex) < self.n_examples and rid not in ex:
                    ex.append(rid)

    def _stats_dict(self, st: _Stats, total: int) -> dict:
        return {
            "records": len(st.records),
            "share": len(st.records) / total if total else 0.0,
            "occurrences": st.occurrences,
            "top_sequences": [
                {"text": t, "shown": display(t), "codepoints": [f"U+{ord(c):04X}" for c in t], "count": c}
                for t, c in st.sequences.most_common(self.n_sequences)
            ],
            "examples": st.examples,
        }

    def sources_summary(self) -> dict:
        total = sum(sum(c.values()) for c in self.by_source.values())
        rows = []
        for src, n in self.source_records.items():
            occ = sum(self.by_source[src].values())
            rows.append(
                {
                    "source": src,
                    "records": n,
                    "damaged_records": len(self.source_damaged[src]),
                    "share": len(self.source_damaged[src]) / n if n else 0.0,
                    "occurrences": occ,
                    "classes": dict(self.by_source[src].most_common()),
                    "examples": self.source_examples.get(src, []),
                }
            )
        rows.sort(key=lambda r: (-r["occurrences"], r["source"]))
        top = rows[: self.n_top_sources]
        return {
            "sources": len(rows),
            "top_k": self.n_top_sources,
            "top_share_of_occurrences": sum(r["occurrences"] for r in top) / total if total else 0.0,
            "top_share_of_records": sum(r["records"] for r in top) / self.records if self.records else 0.0,
            "rows": rows,
        }

    def to_dict(self) -> dict:
        out = {
            "records": self.records,
            "damaged_records": len(self.damaged),
            "classes": {
                c: self._stats_dict(self.by_class[c], self.records) for c in CLASSES if c in self.by_class
            },
            "fields": {
                f: {c: self._stats_dict(st[c], self.field_records[f]) for c in CLASSES if c in st}
                for f, st in sorted(self.by_field.items())
            },
            "input_errors": [{"line": n, "error": m} for n, m in self.input_errors],
            "proposed_repairs": [
                {"class": c, "text": t, "repair": r, "shown": f"{display(t)} -> {display(r)}", "count": n}
                for (c, t, r), n in self.repairs.most_common(10)
            ],
        }
        if self.source_records:
            out["sources"] = self.sources_summary()
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_markdown(self, title: str = "textdamage scan") -> str:
        d = self.to_dict()
        lines = [f"# {title}", ""]
        lines.append(f"Records: {d['records']}; with any damage: {d['damaged_records']}.")
        lines.append("")
        if not d["classes"]:
            lines.append("No damage found.")
        else:
            lines += [
                "| class | records | share | occurrences | commonest sequences | example ids |",
                "|---|---|---|---|---|---|",
            ]
            for c, s in d["classes"].items():
                seqs = ", ".join(f"`{_md(t['shown'])}` x{t['count']}" for t in s["top_sequences"])
                ex = ", ".join(_md(e) for e in s["examples"])
                lines.append(
                    f"| {c} | {s['records']} | {s['share']:.2%} | {s['occurrences']} | {seqs} | {ex} |"
                )
        if len(d["fields"]) > 1:
            lines += ["", "## Per field", "", "| field | class | records | share | occurrences |"]
            lines.append("|---|---|---|---|---|")
            for f, cl in d["fields"].items():
                for c, s in cl.items():
                    lines.append(f"| {_md(f)} | {c} | {s['records']} | {s['share']:.2%} | {s['occurrences']} |")
        if d["proposed_repairs"]:
            lines += ["", "## Proposed mojibake repairs", "", "| class | damaged | repair | occurrences |",
                      "|---|---|---|---|"]
            for r in d["proposed_repairs"]:
                lines.append(f"| {r['class']} | `{_md(display(r['text']))}` | `{_md(display(r['repair']))}` | "
                             f"{r['count']} |")
        if "sources" in d:
            lines += ["", _sources_md(d["sources"])]
        if d["input_errors"]:
            lines += ["", f"Input errors: {len(d['input_errors'])} (first: line {d['input_errors'][0]['line']}, "
                      f"{d['input_errors'][0]['error']})."]
        return "\n".join(lines) + "\n"


def _md(s: str) -> str:
    return str(s).replace("|", "\\|").replace("`", "'")


def _sources_md(s: dict, limit: int = 20) -> str:
    lines = [
        "## Per source",
        "",
        f"Sources: {s['sources']}. The top {s['top_k']} sources by occurrences hold "
        f"{s['top_share_of_occurrences']:.1%} of all occurrences and {s['top_share_of_records']:.1%} of records.",
        "",
        "| source | records | damaged records | share | occurrences | classes | example ids |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in s["rows"][:limit]:
        cl = ", ".join(f"{k} {v}" for k, v in list(r["classes"].items())[:4])
        lines.append(
            f"| {_md(r['source'])} | {r['records']} | {r['damaged_records']} | {r['share']:.2%} | "
            f"{r['occurrences']} | {cl} | {', '.join(_md(e) for e in r['examples'])} |"
        )
    return "\n".join(lines)
