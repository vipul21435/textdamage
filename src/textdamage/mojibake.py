"""Detection and repair of UTF-8 text that was decoded as Latin-1 or Windows-1252.

Rule.  A *mojibake sequence* is a lead character U+00C2..U+00F4 followed by the number of continuation
characters its UTF-8 lead byte asks for, where a continuation character is any character that Latin-1 or
Windows-1252 produces from a byte 0x80..0xBF.  The sequence is mapped back to bytes and decoded as strict UTF-8;
only sequences that decode are candidates.  Touching candidates form a group.  A group is decoded once, and when
the result still contains candidates it is decoded a second time (two rounds of damage).

A repair is proposed only when it is more plausible by this score, ``badness``: the count of control,
surrogate, private-use and unassigned characters, plus characters outside a fixed list of commonly written
script and symbol blocks, plus remaining mojibake sequences.  The repair is accepted only when the repaired
group scores 0 (every candidate group scores at least 1).  Everything else is never changed; a rejected group is
counted as ambiguous when its record also holds an accepted repair, and otherwise treated as ordinary text
(``"ß“"`` in German decodes to an NKo letter and is left alone).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SLOPPY_1252: dict[int, str] = {}
for _b in range(0x80, 0x100):
    try:
        _SLOPPY_1252[_b] = bytes([_b]).decode("cp1252")
    except UnicodeDecodeError:
        _SLOPPY_1252[_b] = chr(_b)  # the five bytes Windows-1252 leaves undefined pass through as C1

TO_BYTE: dict[str, int] = {chr(b): b for b in range(0x80, 0x100)}
TO_BYTE.update({ch: b for b, ch in _SLOPPY_1252.items()})

_CONT = sorted({ch for ch, b in TO_BYTE.items() if 0x80 <= b <= 0xBF})
_C = "[" + "".join(re.escape(c) for c in _CONT) + "]"
SEQ_RE = re.compile(
    "(?:[Â-ß]" + _C + "|[à-ï]" + _C + "{2}|[ð-ô]" + _C + "{3})"
)
_LONE_LEAD_RE = re.compile("[ÂÃ](?= |$)")

# Blocks a repaired character may fall in.  Characters below U+0250 (Latin-1 and Latin Extended-A/B) are
# always allowed.
COMMON_BLOCKS: tuple[tuple[int, int], ...] = (
    (0x02B0, 0x02FF),  # spacing modifier letters
    (0x0300, 0x036F),  # combining diacritical marks
    (0x0370, 0x03FF),  # Greek
    (0x0400, 0x052F),  # Cyrillic
    (0x0530, 0x058F),  # Armenian
    (0x0590, 0x05FF),  # Hebrew
    (0x0600, 0x06FF),  # Arabic
    (0x0900, 0x0DFF),  # Indic scripts through Sinhala
    (0x0E00, 0x0EFF),  # Thai, Lao
    (0x0F00, 0x0FFF),  # Tibetan
    (0x1000, 0x109F),  # Myanmar
    (0x10A0, 0x10FF),  # Georgian
    (0x1100, 0x11FF),  # Hangul jamo
    (0x1200, 0x139F),  # Ethiopic
    (0x1780, 0x17FF),  # Khmer
    (0x1E00, 0x1FFF),  # Latin extended additional, Greek extended
    (0x2000, 0x2BFF),  # punctuation, currency, letterlike, arrows, maths, technical, shapes, symbols
    (0x3000, 0x312F),  # CJK symbols, kana, bopomofo
    (0x3130, 0x318F),  # Hangul compatibility jamo
    (0x3400, 0x4DBF),  # CJK extension A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xAC00, 0xD7AF),  # Hangul syllables
    (0xFE00, 0xFE0F),  # variation selectors
    (0xFF00, 0xFFEF),  # halfwidth and fullwidth forms
    (0x1F000, 0x1FAFF),  # emoji and pictographs
)


def in_common_block(ch: str) -> bool:
    cp = ord(ch)
    if cp < 0x250:
        return True
    return any(lo <= cp <= hi for lo, hi in COMMON_BLOCKS)


def _decode(seq: str) -> str | None:
    try:
        return bytes(TO_BYTE[c] for c in seq).decode("utf-8")
    except (UnicodeDecodeError, KeyError):
        return None


def candidates(text: str) -> list[tuple[int, int, str]]:
    """All mojibake-shaped sequences in ``text`` that decode as strict UTF-8: (start, end, decoded)."""
    out = []
    for m in SEQ_RE.finditer(text):
        dec = _decode(m.group())
        if dec is not None:
            out.append((m.start(), m.end(), dec))
    return out


def badness(text: str) -> int:
    """Plausibility score; 0 means nothing suspicious.  See the module docstring."""
    score = 0
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cs", "Co", "Cn") and ch not in "\t\n\r":
            score += 1
        elif not in_common_block(ch):
            score += 1
    return score + len(candidates(text))


def _apply(text: str, cands: list[tuple[int, int, str]]) -> str:
    parts, pos = [], 0
    for s, e, d in cands:
        parts.append(text[pos:s])
        parts.append(d)
        pos = e
    parts.append(text[pos:])
    return "".join(parts)


@dataclass(frozen=True)
class MojibakeHit:
    start: int
    end: int
    text: str
    fix: str | None  # None when ambiguous
    rounds: int  # 1 or 2; 0 when ambiguous
    sequences: int  # number of mojibake sequences in the hit


def _groups(cands: list[tuple[int, int, str]]) -> list[list[tuple[int, int, str]]]:
    groups: list[list[tuple[int, int, str]]] = []
    for c in cands:
        if groups and groups[-1][-1][1] == c[0]:
            groups[-1].append(c)
        else:
            groups.append([c])
    return groups


def _judge(orig: str, group: list[tuple[int, int, str]]) -> tuple[str | None, int, int]:
    r1 = "".join(d for _, _, d in group)
    if badness(r1) == 0:
        return r1, 1, len(group)
    c2 = candidates(r1)
    if c2:
        r2 = _apply(r1, c2)
        if badness(r2) == 0:
            return r2, 2, len(c2)
    return None, 0, len(group)


def find_mojibake(text: str) -> list[MojibakeHit]:
    """Accepted and ambiguous mojibake hits in ``text``, in order."""
    hits: list[MojibakeHit] = []
    rejected: list[MojibakeHit] = []
    for group in _groups(candidates(text)):
        gs, ge = group[0][0], group[-1][1]
        fix, rounds, n = _judge(text[gs:ge], group)
        if fix is not None:
            hits.append(MojibakeHit(gs, ge, text[gs:ge], fix, rounds, n))
            continue
        # fall back to single sequences inside a group that failed as a whole
        for s, e, _ in group if len(group) > 1 else []:
            f1, r, n1 = _judge(text[s:e], [(s, e, _decode(text[s:e]) or "")])
            if f1 is not None:
                hits.append(MojibakeHit(s, e, text[s:e], f1, r, n1))
            else:
                rejected.append(MojibakeHit(s, e, text[s:e], None, 0, 1))
        if len(group) == 1:
            rejected.append(MojibakeHit(gs, ge, text[gs:ge], None, 0, n))
    if hits:
        taken = [(h.start, h.end) for h in hits]
        for m in _LONE_LEAD_RE.finditer(text):
            if not any(s <= m.start() < e for s, e in taken):
                rejected.append(MojibakeHit(m.start(), m.end(), m.group(), None, 0, 1))
        hits.extend(rejected)
    hits.sort(key=lambda h: h.start)
    return hits


def repair_mojibake(text: str) -> str:
    """``text`` with every accepted mojibake hit replaced; ambiguous hits are left as they are."""
    parts, pos = [], 0
    for h in find_mojibake(text):
        if h.fix is None:
            continue
        parts.append(text[pos : h.start])
        parts.append(h.fix)
        pos = h.end
    parts.append(text[pos:])
    return "".join(parts)


def make_mojibake(text: str, encoding: str = "cp1252", rounds: int = 1) -> str:
    """Damage ``text`` the usual way: encode as UTF-8, decode as ``encoding`` (``cp1252`` passes the five
    undefined bytes through as C1 controls, as many real decoders do)."""
    for _ in range(rounds):
        data = text.encode("utf-8")
        if encoding == "cp1252":
            text = "".join(chr(b) if b < 0x80 else _SLOPPY_1252[b] for b in data)
        else:
            text = data.decode(encoding)
    return text
