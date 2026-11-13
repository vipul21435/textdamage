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
    p.write_text(json.dumps([{"meta": {"src": "s1"}, "t": "a\ufffd"}, {"meta": {"src": "s2"}, "t": "b"}]))
    rep = scan_file(p, source_field="meta.src")
    d = rep.to_dict()
    assert d["classes"]["replacement"]["records"] == 1
    assert {r["source"] for r in d["sources"]["rows"]} == {"s1", "s2"}
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2")
    assert len(scan_file(bad).input_errors) == 1


def test_csv_and_tsv(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text('id,src,text\n1,a,"x\u200by"\n2,b,"multi\nline \ufffd"\n3,a\n', encoding="utf-8")
    rep = scan_file(p, source_field="src")
    d = rep.to_dict()
    assert d["records"] == 2 and len(d["input_errors"]) == 1
    assert set(d["fields"]) == {"text"}
    t = tmp_path / "d.tsv"
    t.write_text("text\tlang\nzero\u200bwidth\ten\n", encoding="utf-8")
    assert scan_file(t, fields=["text"]).to_dict()["classes"]["invisible"]["records"] == 1
    empty = tmp_path / "e.csv"
    empty.write_text("")
    assert scan_file(empty).records == 0


def test_txt_gz_and_limit(tmp_path):
    p = tmp_path / "d.txt.gz"
    p.write_bytes(gzip.compress("\ufeffone \u200b\ntwo\nthree \ufffd\n".encode()))
    assert scan_file(p).to_dict()["classes"]["invisible"]["records"] == 1
    assert scan_file(p, limit=2).records == 2
    md = scan_file(p).to_markdown()
    assert "invisible" in md and "<U+200B>" in md


def test_reservoir_sample_is_uniform_and_seeded():
    from collections import Counter

    from textdamage.scan import reservoir

    assert reservoir(range(5), 10) == [0, 1, 2, 3, 4]
    assert reservoir(range(100), 5, seed=1) == reservoir(range(100), 5, seed=1)
    hits = Counter()
    for seed in range(2000):
        hits.update(reservoir(range(10), 3, seed=seed))
    # each item is kept with probability 3/10: 600 expected per item out of 2000 draws
    assert all(abs(hits[i] - 600) < 90 for i in range(10))
    try:
        reservoir(range(3), -1)
    except ValueError:
        pass


def test_scan_sample(tmp_path):
    p = tmp_path / "d.txt"
    p.write_text("".join(f"line {i}\n" for i in range(50)))
    assert scan_file(p, sample=10, seed=4).records == 10
