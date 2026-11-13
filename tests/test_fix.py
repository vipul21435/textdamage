import csv
import gzip
import io
import json
import random

import pytest

from tests.test_mojibake import SAMPLES
from textdamage.cli import main
from textdamage.fixer import fix_file, repair_text
from textdamage.mojibake import make_mojibake


def test_repair_text_classes():
    text = "caf\u00c3\u00a9\ufeff\x00\x85 zero\u200bwidth e\u0301 a\u200db"
    new, changes = repair_text(text, ["mojibake", "bom", "c0", "c1", "invisible", "non-nfc"])
    assert new == "caf\u00e9 zerowidth \u00e9 a\u200db"
    assert [c.cls for c in changes] == ["mojibake", "bom", "c0", "c1", "invisible", "non-nfc"]
    with pytest.raises(ValueError):
        repair_text("x", ["confusable"])


def test_repair_respects_ignore_list():
    new, _ = repair_text("a\u200bb", ["invisible"], frozenset({"\u200b"}))
    assert new == "a\u200bb"


def _dataset(rng, n=200):
    rows = []
    for i in range(n):
        clean = rng.choice(SAMPLES)
        damaged = rng.random() < 0.3
        rows.append({"id": f"item-{i}", "text": make_mojibake(clean) if damaged else clean,
                     "meta": {"n": i, "tags": ["x", clean[:5]]}})
    return rows


def test_fix_jsonl_never_changes_undamaged_records(tmp_path):
    rng = random.Random(3)
    rows = _dataset(rng)
    src = tmp_path / "in.jsonl"
    # mixed serialisation styles: compact, spaced and ASCII-escaped lines must all survive byte for byte
    lines = []
    for i, r in enumerate(rows):
        style = i % 3
        if style == 0:
            lines.append(json.dumps(r, ensure_ascii=False))
        elif style == 1:
            lines.append(json.dumps(r, separators=(",", ":")))
        else:
            lines.append(json.dumps(r, indent=None, sort_keys=True))
    data = ("\n".join(lines) + "\n\n").encode()
    src.write_bytes(data)
    out = tmp_path / "out.jsonl"
    res = fix_file(src, out)
    assert res.ok and res.records == len(rows)
    in_lines = data.splitlines(keepends=True)
    out_lines = out.read_bytes().splitlines(keepends=True)
    assert len(in_lines) == len(out_lines)
    for a, b, line in zip(in_lines, out_lines, in_lines, strict=True):
        if not line.strip():
            assert a == b
            continue
        if json.loads(a)["text"] in SAMPLES:
            assert a == b
        else:
            assert json.loads(b)["text"] in SAMPLES
    log = [json.loads(x) for x in (tmp_path / "out.jsonl.changes.jsonl").read_text().splitlines()]
    assert {e["class"] for e in log} == {"mojibake"}
    assert res.changed == sum(json.loads(a)["text"] not in SAMPLES for a in in_lines if a.strip())


def test_fix_refuses_in_place_and_existing_output(tmp_path):
    src = tmp_path / "in.jsonl"
    src.write_text('{"t": "x"}\n')
    with pytest.raises(ValueError, match="in place"):
        fix_file(src, src)
    out = tmp_path / "out.jsonl"
    out.write_text("")
    with pytest.raises(ValueError, match="exists"):
        fix_file(src, out)
    assert fix_file(src, out, force=True).ok
    with pytest.raises(ValueError, match="JSON arrays"):
        fix_file(tmp_path / "a.json", tmp_path / "b.json")


def test_fix_csv_keeps_unchanged_rows_byte_identical(tmp_path):
    src = tmp_path / "in.csv"
    raw = ('\ufeffid,text,note\r\n1,"plain, quoted",ok\r\n2,caf\u00c3\u00a9,"multi\r\nline"\r\n'
           '3,  spaced  ,"say ""hi"""\r\n')
    src.write_bytes(raw.encode())
    out = tmp_path / "out.csv"
    res = fix_file(src, out)
    assert res.ok and res.changed == 1 and res.unchanged_identical == 2
    got = out.read_bytes().decode()
    assert got.startswith('\ufeffid,text,note\r\n1,"plain, quoted",ok\r\n')
    assert got.endswith('3,  spaced  ,"say ""hi"""\r\n')
    rows = list(csv.reader(io.StringIO(got.removeprefix("\ufeff"), newline="")))
    assert rows[2] == ["2", "caf\u00e9", "multi\r\nline"]


def test_fix_txt_and_gzip(tmp_path):
    src = tmp_path / "in.txt.gz"
    src.write_bytes(gzip.compress("clean line\ncaf\u00c3\u00a9\nno newline".encode()))
    out = tmp_path / "out.txt"
    res = fix_file(src, out)
    assert res.ok
    assert out.read_text() == "clean line\ncaf\u00e9\nno newline"


def test_fix_keeps_invalid_utf8_and_malformed_lines(tmp_path):
    src = tmp_path / "in.jsonl"
    data = b'{"t": "ok"}\n{broken json\n{"t": "bad \xff byte"}\n{"t": "caf\xc3\x83\xc2\xa9"}\n'
    src.write_bytes(data)
    out = tmp_path / "out.jsonl"
    res = fix_file(src, out)
    assert res.ok and len(res.input_errors) == 1
    lines = out.read_bytes().splitlines(keepends=True)
    assert lines[:3] == data.splitlines(keepends=True)[:3]
    assert json.loads(lines[3]) == {"t": "caf\u00e9"}


def test_fix_field_filter(tmp_path):
    src = tmp_path / "in.jsonl"
    src.write_text(json.dumps({"a": "caf\u00c3\u00a9", "b": "caf\u00c3\u00a9"}) + "\n")
    out = tmp_path / "out.jsonl"
    fix_file(src, out, fields=["a"])
    assert json.loads(out.read_text()) == {"a": "caf\u00e9", "b": "caf\u00c3\u00a9"}


def test_fix_cli(tmp_path, capsys):
    src = tmp_path / "in.jsonl"
    src.write_text(json.dumps({"id": 1, "t": "x\u200by"}) + "\n")
    out = tmp_path / "out.jsonl"
    assert main(["fix", str(src), str(out), "--repair", "invisible", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["changed_records"] == 1 and d["changes"] == {"invisible": 1}
    assert main(["fix", str(src), str(src)]) == 2


def test_change_log_escapes_invisible_characters(tmp_path):
    src = tmp_path / "in.jsonl"
    src.write_text(json.dumps({"id": 7, "t": "x\u200by"}) + "\n")
    out = tmp_path / "out.jsonl"
    fix_file(src, out, repairs=["invisible"])
    raw = (tmp_path / "out.jsonl.changes.jsonl").read_text()
    assert "\\u200b" in raw and raw.isascii()
    expected = {"id": "7", "line": 1, "field": "t", "class": "invisible", "before": "\u200b", "after": ""}
    assert json.loads(raw) == expected
