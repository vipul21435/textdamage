"""Check the confusable table against the Unicode confusables.txt data file (UTS #39).

Usage: python scripts/check_confusables.py path/to/confusables.txt

Download the file from https://www.unicode.org/Public/security/latest/confusables.txt first.  Prints every
pair of the table that the file does not list as a one-to-one mapping, and exits 1 when there is one.
"""

from __future__ import annotations

import sys

from textdamage.chars import CONFUSABLE_TO_LATIN


def load(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            src, dst = (part.strip() for part in line.split(";")[:2])
            if " " in src or " " in dst:
                continue
            out[chr(int(src, 16))] = chr(int(dst, 16))
    return out


def main(argv: list[str]) -> int:
    table = load(argv[1])
    bad = []
    for ch, latin in CONFUSABLE_TO_LATIN.items():
        target = table.get(ch)
        # confusables.txt maps to a skeleton; uppercase Latin letters often map to themselves or to a
        # lowercase skeleton, so accept a match on either case.
        latin_skel = table.get(latin, latin)
        if target is None or (target != latin and target != latin_skel and target.lower() != latin.lower()):
            bad.append((f"U+{ord(ch):04X}", latin, None if target is None else f"U+{ord(target):04X}"))
    print(f"pairs in table: {len(CONFUSABLE_TO_LATIN)}; not confirmed by the data file: {len(bad)}")
    for row in bad:
        print("  ", *row)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
