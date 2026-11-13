import gzip
import json

from textdamage.io import InputErrors, detect_format, iter_records, walk_strings
from textdamage.scan import scan_file


def test_detect_format():
    assert detect_format("a.jsonl.gz") == "jsonl"
    assert detect_format("a.ndjson") == "jsonl"
    assert detect_format("a.json") == "json"
    assert detect_format("a.csv") == "csv"
    assert detect_format("a.TSV") == "tsv"
    assert detect_format("a.txt") == "txt"


def test_walk_strings_paths():
    obj = {"id": 1, "messages": [{"role": "user", "content": "hi"}, {"role": "a", "content": "yo"}], "x": None}
    assert list(walk_strings(obj)) == [
        ("messages[].role", "user"), ("messages[].content", "hi"),
        ("messages[].role", "a"), ("messages[].content", "yo"),
    ]


def test_malformed_jsonl_is_reported_and_skipped(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_bytes(b'\xef\xbb\xbf{"id": "a", "t": "x"}\n{oops\n\n"just a string"\n[1, 2]\n{"t": "bad \xfe"}\n')
    errors = InputErrors()
    recs = [r for r in iter_records(p, errors=errors) if not r.passthrough]
    assert [r.rid for r in recs] == ["a", "4", "5", "6"]
    assert errors.items[0][0] == 2
    rep = scan_file(p)
    assert rep.records == 4 and len(rep.input_errors) == 1
    assert rep.to_dict()["classes"]["surrogate"]["records"] == 1


def test_json_array_and_nested_source(tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps([{"meta": {"src": "s1"}, "t": "a�"}, {"meta": {"src": "s2"}, "t": "b"}]))
    rep = scan_file(p, source_field="meta.src")
    d = rep.to_dict()
    assert d["classes"]["replacement"]["records"] == 1
    assert {r["source"] for r in d["sources"]["rows"]} == {"s1", "s2"}
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2")
    assert len(scan_file(bad).input_errors) == 1


def test_csv_and_tsv(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text('id,src,text\n1,a,"x​y"\n2,b,"multi\nline �"\n3,a\n', encoding="utf-8")
    rep = scan_file(p, source_field="src")
    d = rep.to_dict()
    assert d["records"] == 2 and len(d["input_errors"]) == 1
    assert set(d["fields"]) == {"text"}
    t = tmp_path / "d.tsv"
    t.write_text("text\tlang\nzero​width\ten\n", encoding="utf-8")
    assert scan_file(t, fields=["text"]).to_dict()["classes"]["invisible"]["records"] == 1
    empty = tmp_path / "e.csv"
    empty.write_text("")
    assert scan_file(empty).records == 0


def test_txt_gz_and_limit(tmp_path):
    p = tmp_path / "d.txt.gz"
    p.write_bytes(gzip.compress("﻿one ​\ntwo\nthree �\n".encode()))
    assert scan_file(p).to_dict()["classes"]["invisible"]["records"] == 1
    assert scan_file(p, limit=2).records == 2
    md = scan_file(p).to_markdown()
    assert "invisible" in md and "<U+200B>" in md
