"""Detectors.  Each one has a documented rule and returns findings with positions.

Class names, in report order:

- ``mojibake``: UTF-8 decoded once as Latin-1 or Windows-1252, repair accepted (see ``textdamage.mojibake``).
- ``mojibake-2``: the same damage applied twice, repair accepted.
- ``mojibake-ambiguous``: mojibake-shaped text in a string that has accepted repairs, but whose own repair
  failed the plausibility rule (or a lone ``\\u00c2``/``\\u00c3`` before a space, where the second byte was
  lost).  Never changed.
- ``replacement``: U+FFFD.
- ``c0``: C0 controls other than tab, LF and CR, and DEL.
- ``c1``: C1 controls U+0080..U+009F that are not part of an accepted mojibake hit.
- ``invisible``: zero-width and other invisible characters (``chars.INVISIBLE``), except joiners, variation
  selectors and tags in the contexts where they have a known use (``chars.invisible_is_legitimate``).
- ``bidi``: explicit directional formatting characters of UAX #9 and U+061C.
- ``bom``: U+FEFF inside a field value (a byte-order mark at the very start of a file is removed by the
  reader and not counted).
- ``non-nfc``: a combining sequence (a starter and the non-starters after it) that NFC normalisation changes.
- ``compat``: compatibility characters of a formatting kind: decomposition tag ``<font>``, ``<narrow>``,
  ``<circle>``, ``<square>``, ``<small>``, ``<vertical>``, ``<wide>`` letters, digits and symbols (fullwidth
  punctuation is ordinary in CJK text and not counted), or a Latin ligature U+FB00..U+FB06.
- ``confusable``: a word (run of letters and marks) mixing Latin with Cyrillic or Greek letters in which the
  minority-script letters are in the confusable table (``chars.CONFUSABLE_TO_LATIN``).  One per word.
- ``escape``: literal backslash escapes ``\\n``, ``\\t``, ``\\r`` (not followed by a lowercase letter, so LaTeX
  commands such as ``\\theta`` are skipped), ``\\uXXXX``, ``\\UXXXXXXXX``, ``\\xXX``, outside Markdown code.
- ``entity``: an HTML character reference (``&amp;``, ``&#233;``, ``&#xE9;`` or any HTML5 named reference with
  its semicolon) outside Markdown code.
- ``surrogate``: a lone surrogate code point.  Bytes that are not valid UTF-8 in an input file are read as lone
  surrogates U+DC80..U+DCFF and land here.
- ``repeat``: a run of at least ``repeat_min`` identical punctuation characters, or of horizontal whitespace
  inside a line (indentation is skipped), or of blank lines, outside Markdown code.  Punctuation runs that
  fill a whole line or sit in a Markdown table row are skipped.
"""

from __future__ import annotations

import html.entities
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from . import chars
from .mojibake import find_mojibake

CLASSES: tuple[str, ...] = (
    "mojibake",
    "mojibake-2",
    "mojibake-ambiguous",
    "replacement",
    "c0",
    "c1",
    "invisible",
    "bidi",
    "bom",
    "non-nfc",
    "compat",
    "confusable",
    "escape",
    "entity",
    "surrogate",
    "repeat",
)


@dataclass(frozen=True)
class Finding:
    cls: str
    start: int
    end: int
    text: str
    fix: str | None = None


_CODE_RE = re.compile(r"```.*?(?:```|\Z)|`[^`\n]+`", re.S)
_ESCAPE_RE = re.compile(r"\\(?:[nrt](?![a-z])|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|x[0-9a-fA-F]{2})")
_ENTITY_RE = re.compile(r"&(?:#[0-9]{1,7};|#[xX][0-9a-fA-F]{1,6};|[A-Za-z][A-Za-z0-9]{1,31};)")
_HTML5 = frozenset(html.entities.html5)
_WORD_RE = re.compile(r"[^\W\d_](?:[^\W\d_]|[\u0300-\u036f])*")


def _masked(text: str, fill: str = " ") -> str:
    """``text`` with Markdown code spans and fences replaced by ``fill`` (same length, newlines kept)."""
    return _CODE_RE.sub(lambda m: "".join(c if c == "\n" else fill for c in m.group()), text)


def _char_class(text: str, table: frozenset[str], cls: str) -> list[Finding]:
    return [Finding(cls, i, i + 1, ch) for i, ch in enumerate(text) if ch in table]


def detect_invisible(text: str) -> list[Finding]:
    out = []
    for i, ch in enumerate(text):
        if ch in chars.INVISIBLE and not chars.invisible_is_legitimate(text, i):
            out.append(Finding("invisible", i, i + 1, ch))
    return out


def detect_non_nfc(text: str) -> list[Finding]:
    if unicodedata.is_normalized("NFC", text):
        return []
    out = []
    i, n = 0, len(text)
    while i < n:
        j = i + 1
        while j < n and unicodedata.combining(text[j]):
            j += 1
        seg = text[i:j]
        if not unicodedata.is_normalized("NFC", seg):
            out.append(Finding("non-nfc", i, j, seg, unicodedata.normalize("NFC", seg)))
        i = j
    if not out:  # composition across starters (conjoining Hangul jamo)
        out.append(Finding("non-nfc", 0, len(text), text[:8], None))
    return out


def detect_compat(text: str) -> list[Finding]:
    return [Finding("compat", i, i + 1, ch) for i, ch in enumerate(text) if ord(ch) > 0x7F and chars.is_compat(ch)]


def detect_confusable(text: str) -> list[Finding]:
    out = []
    for m in _WORD_RE.finditer(text):
        word = m.group()
        counts: dict[str, int] = {}
        for ch in word:
            s = chars.script_of(ch)
            if s in ("LATIN", "CYRILLIC", "GREEK"):
                counts[s] = counts.get(s, 0) + 1
        if len(counts) < 2:
            continue
        latin = counts.get("LATIN", 0)
        other = sum(v for k, v in counts.items() if k != "LATIN")
        if latin >= other:
            odd = [ch for ch in word if ch in chars.CONFUSABLE_TO_LATIN]
        else:
            odd = [ch for ch in word if ch in chars.LATIN_TO_CONFUSABLE]
        if odd:
            out.append(Finding("confusable", m.start(), m.end(), "".join(odd)))
    return out


def detect_escapes(text: str) -> list[Finding]:
    masked = _masked(text)
    out = [Finding("escape", m.start(), m.end(), m.group()) for m in _ESCAPE_RE.finditer(masked)]
    for m in _ENTITY_RE.finditer(masked):
        name = m.group()[1:]
        if name.startswith("#") or name in _HTML5:
            out.append(Finding("entity", m.start(), m.end(), m.group()))
    return out


def detect_repeats(text: str, repeat_min: int = 10) -> list[Finding]:
    if repeat_min < 2:
        raise ValueError("repeat_min must be at least 2")
    out = []
    text = _masked(text, "x")
    for m in re.finditer("[ \t\u00a0\u3000]{%d,}" % repeat_min, text):
        if m.start() == 0 or text[m.start() - 1] == "\n" or m.end() == len(text) or text[m.end()] == "\n":
            continue  # indentation and trailing space
        out.append(Finding("repeat", m.start(), m.end(), m.group()[:3]))
    for m in re.finditer(r"(?:\r?\n[ \t]*){%d,}" % repeat_min, text):
        out.append(Finding("repeat", m.start(), m.end(), "\n\n\n"))
    for m in re.finditer(r"([^\w\s])\1{%d,}" % (repeat_min - 1), text):
        if not unicodedata.category(m.group(1)).startswith(("P", "S")):
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start : len(text) if line_end < 0 else line_end].strip()
        if line == m.group() or line.startswith("|"):
            continue
        out.append(Finding("repeat", m.start(), m.end(), m.group()[:3]))
    return out


def scan_text(
    text: str,
    *,
    repeat_min: int = 10,
    ignore: Iterable[str] = (),
    classes: Iterable[str] | None = None,
) -> list[Finding]:
    """Every finding in ``text``, sorted by position.

    ``ignore`` is a collection of characters a project accepts: a finding whose text consists only of ignored
    characters is dropped.  ``classes`` limits the detectors that run.
    """
    want = set(CLASSES if classes is None else classes)
    unknown = want - set(CLASSES)
    if unknown:
        raise ValueError(f"unknown classes: {sorted(unknown)}")
    found: list[Finding] = []
    taken: list[tuple[int, int]] = []
    if want & {"mojibake", "mojibake-2", "mojibake-ambiguous"}:
        for h in find_mojibake(text):
            cls = "mojibake-ambiguous" if h.fix is None else ("mojibake-2" if h.rounds == 2 else "mojibake")
            if h.fix is not None:
                taken.append((h.start, h.end))
            found.append(Finding(cls, h.start, h.end, h.text, h.fix))
    found += _char_class(text, frozenset(chars.REPLACEMENT), "replacement")
    found += _char_class(text, chars.C0, "c0")
    found += [
        f for f in _char_class(text, chars.C1, "c1") if not any(s <= f.start < e for s, e in taken)
    ]
    found += detect_invisible(text)
    found += _char_class(text, chars.BIDI, "bidi")
    found += _char_class(text, frozenset(chars.BOM), "bom")
    if "non-nfc" in want:
        found += detect_non_nfc(text)
    if "compat" in want:
        found += detect_compat(text)
    if "confusable" in want:
        found += detect_confusable(text)
    if want & {"escape", "entity"}:
        found += detect_escapes(text)
    found += [Finding("surrogate", i, i + 1, ch) for i, ch in enumerate(text) if 0xD800 <= ord(ch) <= 0xDFFF]
    if "repeat" in want:
        found += detect_repeats(text, repeat_min)
    ign = set(ignore)
    found = [f for f in found if f.cls in want and not (ign and set(f.text) <= ign)]
    found.sort(key=lambda f: (f.start, CLASSES.index(f.cls)))
    return found
