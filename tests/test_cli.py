import json

from textdamage.cli import main


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_scan_json_report(tmp_path, capsys):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, [
        {"id": "a", "src": "x", "text": "caf\u00c3\u00a9"},
        {"id": "b", "src": "y", "text": "clean"},
        {"id": "c", "src": "x", "text": "zero\u200bwidth"},
    ])
    assert main(["scan", str(p), "--source-field", "src", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["records"] == 3 and d["damaged_records"] == 2
    assert d["classes"]["mojibake"]["records"] == 1
    assert d["classes"]["mojibake"]["top_sequences"][0]["text"] == "\u00c3\u00a9"
    assert d["classes"]["invisible"]["examples"] == ["c"]
    assert d["sources"]["rows"][0]["source"] == "x"
    assert d["sources"]["top_share_of_occurrences"] == 1.0


def test_scan_markdown_and_field_filter(tmp_path, capsys):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, [{"q": "a\ufffd", "a": "b\u200b"}])
    assert main(["scan", str(p), "--field", "q"]) == 0
    out = capsys.readouterr().out
    assert "replacement" in out and "invisible" not in out


def test_explain(capsys):
    assert main(["explain", "-e", "caf\\u00c3\\u00a9"]) == 0
    out = capsys.readouterr().out
    assert "U+00C3" in out and "mojibake" in out
    assert main(["explain", "--json", "a\u200bb"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["findings"][0]["class"] == "invisible"


def test_missing_file_is_exit_2(tmp_path, capsys):
    assert main(["scan", str(tmp_path / "nope.jsonl")]) == 2


def test_limits_exit_code(tmp_path, capsys):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, [{"t": "caf\u00c3\u00a9"}, {"t": "clean"}, {"t": "clean"}, {"t": "clean"}])
    assert main(["scan", str(p), "--max", "mojibake=1"]) == 0
    assert main(["scan", str(p), "--max", "mojibake=0"]) == 1
    assert main(["scan", str(p), "--max", "any=30%"]) == 0
    assert main(["scan", str(p), "--max", "any=20%"]) == 1
    assert main(["scan", str(p), "--max", "invisible=0"]) == 0
    assert main(["scan", str(p), "--max", "nope=1"]) == 2
    assert main(["scan", str(p), "--max", "mojibake"]) == 2
    assert "limit exceeded" in capsys.readouterr().err


def test_ignore_flags(tmp_path, capsys):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, [{"t": "a\u200db\u200bc\ufe0e"}])
    ig = tmp_path / "ignore.txt"
    ig.write_text("# accepted\nU+FE00..U+FE0F\n")
    assert main(["scan", str(p), "--json", "--ignore", "U+200D", "--ignore", "200b", "--ignore-file", str(ig)]) == 0
    d = json.loads(capsys.readouterr().out)
    assert "invisible" not in d["classes"]


def test_sources_command(tmp_path, capsys):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, [
        {"url": "https://a.example/x", "t": "caf\u00c3\u00a9"},
        {"url": "https://a.example/y", "t": "caf\u00c3\u00a9 \ufffd"},
        {"url": "https://b.example/z", "t": "x\u200by"},
        {"url": "https://c.example/z", "t": "clean"},
    ])
    assert main(["sources", str(p), "--source-field", "url", "--source-host", "--json", "--top-sources", "1"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["rows"][0]["source"] == "a.example" and s["rows"][0]["occurrences"] == 3
    assert s["top_share_of_occurrences"] == 0.75
    assert main(["sources", str(p), "--source-field", "url"]) == 0
    assert "| https://a.example/x |" in capsys.readouterr().out
    assert main(["sources", str(p)]) == 2


def test_classes_flag_and_output_file(tmp_path, capsys):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, [{"t": "caf\u00c3\u00a9 \u200b"}])
    out = tmp_path / "r.md"
    assert main(["scan", str(p), "--classes", "invisible", "-o", str(out)]) == 0
    text = out.read_text()
    assert "invisible" in text and "mojibake" not in text
    try:
        main(["scan", str(p), "--classes", "bogus"])
    except SystemExit as exc:
        assert "unknown class" in str(exc)


def test_report_lists_proposed_repairs(tmp_path, capsys):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, [{"t": "caf\u00c3\u00a9 \u00c3\u00a9t\u00c3\u00a9"}, {"t": "it\u00e2\u0080\u0099s"}])
    assert main(["scan", str(p), "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    top = d["proposed_repairs"][0]
    assert (top["text"], top["repair"], top["count"]) == ("\u00c3\u00a9", "\u00e9", 3)
    assert main(["scan", str(p)]) == 0
    assert "## Proposed mojibake repairs" in capsys.readouterr().out
