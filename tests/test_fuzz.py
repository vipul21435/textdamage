"""Seeded fuzzing of the readers and of fix on random bytes."""

import json
import random

import pytest

from textdamage.fixer import fix_file
from textdamage.scan import scan_file

ALPHABET = [b"a", b"b", b" ", b",", b'"', b"\n", b"\r\n", b"\r", b"{", b"}", b":", b"\\", b"\x00", b"\x07",
            b"\xc3\xa9", b"\xc3\x83\xc2\xa9", b"\xe2\x80\x8b", b"\xff", b"\xc3", b"\xef\xbb\xbf", b"\\u00e9",
            b"&amp;", b"\xe2\x80\xae"]


def random_bytes(rng, n):
    return b"".join(rng.choice(ALPHABET) for _ in range(n))


def random_jsonl(rng, n):
    lines = []
    for _ in range(n):
        if rng.random() < 0.2:
            lines.append(random_bytes(rng, rng.randint(0, 20)).replace(b"\n", b" ").replace(b"\r", b" "))
        else:
            text = random_bytes(rng, rng.randint(0, 20)).decode("utf-8", "surrogateescape")
            obj = {"id": len(lines), "t": text.replace("\n", " "), "n": [text[:3]]}
            lines.append(json.dumps(obj, ensure_ascii=rng.random() < 0.5).encode("utf-8", "surrogateescape"))
    return b"\n".join(lines) + (b"\n" if rng.random() < 0.5 else b"")


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("suffix", [".jsonl", ".csv", ".txt"])
def test_random_files_never_crash_and_round_trip(tmp_path, seed, suffix):
    rng = random.Random(seed)
    if suffix == ".jsonl":
        data = random_jsonl(rng, 30)
    else:
        data = random_bytes(rng, 300)
    src = tmp_path / f"in{suffix}"
    src.write_bytes(data)
    scan_file(src)
    out = tmp_path / f"out{suffix}"
    res = fix_file(src, out, repairs=["mojibake", "bom", "c0", "c1", "invisible", "non-nfc"])
    assert res.ok, res.mismatches
    if res.changed == 0:
        assert out.read_bytes() == data
