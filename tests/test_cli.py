import json

from textdamage.cli import main


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_scan_json_report(tmp_path, capsys):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, [
        {"id": "a", "src": "x", "text": "cafÃ©"},
        {"id": "b", "src": "y", "text": "clean"},
        {"id": "c", "src": "x", "text": "zero​width"},
    ])
    assert main(["scan", str(p), "--source-field", "src", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["records"] == 3 and d["damaged_records"] == 2
    assert d["classes"]["mojibake"]["records"] == 1
    assert d["classes"]["mojibake"]["top_sequences"][0]["text"] == "Ã©"
    assert d["classes"]["invisible"]["examples"] == ["c"]
    assert d["sources"]["rows"][0]["source"] == "x"
    assert d["sources"]["top_share_of_occurrences"] == 1.0


def test_scan_markdown_and_field_filter(tmp_path, capsys):
    p = tmp_path / "d.jsonl"
    write_jsonl(p, [{"q": "a�", "a": "b​"}])
    assert main(["scan", str(p), "--field", "q"]) == 0
    out = capsys.readouterr().out
    assert "replacement" in out and "invisible" not in out


def test_explain(capsys):
    assert main(["explain", "-e", "caf\\u00c3\\u00a9"]) == 0
    out = capsys.readouterr().out
    assert "U+00C3" in out and "mojibake" in out
    assert main(["explain", "--json", "a​b"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["findings"][0]["class"] == "invisible"


def test_missing_file_is_exit_2(tmp_path, capsys):
    assert main(["scan", str(tmp_path / "nope.jsonl")]) == 2
