"""Character tables used by the detectors.

Every table here is small and written out by hand so that the rule behind each count can be read in one place.
"""

from __future__ import annotations

import unicodedata


def _cps(*items: int | tuple[int, int]) -> frozenset[str]:
    out: set[str] = set()
    for item in items:
        if isinstance(item, tuple):
            out.update(chr(c) for c in range(item[0], item[1] + 1))
        else:
            out.add(chr(item))
    return frozenset(out)


# C0 controls other than tab, line feed and carriage return, plus DEL.
C0 = _cps((0x00, 0x08), 0x0B, 0x0C, (0x0E, 0x1F), 0x7F)
# C1 controls.
C1 = _cps((0x80, 0x9F))

# Explicit directional formatting characters (UAX #9, section 2) and the Arabic letter mark.
BIDI = _cps(0x061C, 0x200E, 0x200F, (0x202A, 0x202E), (0x2066, 0x2069))

BOM = "\ufeff"
REPLACEMENT = "\ufffd"

# Zero-width and other invisible characters.  Joiners and variation selectors have legitimate uses; see
# ``invisible_is_legitimate`` for the contexts that are not counted.
INVISIBLE = _cps(
    0x00AD,  # soft hyphen
    0x034F,  # combining grapheme joiner
    0x115F,
    0x1160,  # Hangul choseong / jungseong fillers
    0x17B4,
    0x17B5,  # Khmer inherent vowels
    0x180E,  # Mongolian vowel separator
    (0x200B, 0x200D),  # zero width space, non-joiner, joiner
    (0x2060, 0x2064),  # word joiner and invisible operators
    (0x206A, 0x206F),  # deprecated format characters
    0x3164,  # Hangul filler
    (0xFE00, 0xFE0F),  # variation selectors
    0xFFA0,  # halfwidth Hangul filler
    0xE0001,
    (0xE0020, 0xE007F),  # tag characters
)

# Invisible characters that ``fix`` may delete: they carry no meaning in running text.
REMOVABLE_INVISIBLE = _cps(0x00AD, 0x180E, 0x200B, (0x2060, 0x2064), (0x206A, 0x206F))

ZWJ = "\u200d"
ZWNJ = "\u200c"
VARIATION_SELECTORS = _cps((0xFE00, 0xFE0F))
TAGS = _cps(0xE0001, (0xE0020, 0xE007F))
BLACK_FLAG = "\U0001f3f4"

# Decomposition tags that mark a compatibility character as a formatting variant of an ordinary one.
COMPAT_TAGS = frozenset({"<font>", "<wide>", "<narrow>", "<circle>", "<square>", "<small>", "<vertical>"})
LIGATURES = _cps((0xFB00, 0xFB06))


def script_of(ch: str) -> str:
    """Approximate script of a letter from the first word of its Unicode name.

    Python's ``unicodedata`` has no Script property; the first word of the character name ("LATIN",
    "CYRILLIC", "GREEK", ...) is a close stand-in for letters.  Returns "" for characters with no name.
    """
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return ""
    return name.split(" ", 1)[0]


def invisible_is_legitimate(text: str, i: int) -> bool:
    """True when the invisible character at ``text[i]`` sits in a context where it has a known use.

    - a zero width joiner or a variation selector right after a symbol (emoji sequences);
    - a zero width non-joiner between two letters of a script other than Latin (Persian, Indic scripts);
    - tag characters that continue a black flag (subdivision flags).
    """
    ch = text[i]
    prev = text[i - 1] if i > 0 else ""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if ch == ZWJ or ch in VARIATION_SELECTORS:
        if prev and (unicodedata.category(prev) in ("So", "Sk") or prev in VARIATION_SELECTORS):
            return True
        if prev and 0x1F3FB <= ord(prev) <= 0x1F3FF:  # skin tone modifiers
            return True
        return False
    if ch == ZWNJ:
        if prev and nxt and unicodedata.category(prev)[0] in "LM" and unicodedata.category(nxt)[0] in "LM":
            return script_of(prev) != "LATIN" and script_of(nxt) != "LATIN"
        return False
    if ch in TAGS:
        j = i - 1
        while j >= 0 and text[j] in TAGS:
            j -= 1
        return j >= 0 and text[j] == BLACK_FLAG
    return False


def is_compat(ch: str) -> bool:
    """Compatibility character of a formatting kind (fullwidth, mathematical, circled, ligature...).

    Fullwidth punctuation and the ideographic space are ordinary in Chinese and Japanese text, so a ``<wide>``
    character counts only when it is a letter, digit or symbol.
    """
    if ch in LIGATURES:
        return True
    dec = unicodedata.decomposition(ch)
    if not dec:
        return False
    tag = dec.split(" ", 1)[0]
    if tag == "<wide>":
        return unicodedata.category(ch)[0] in "LNS"
    return tag in COMPAT_TAGS


# Cyrillic and Greek letters that UTS #39 confusables.txt lists as confusable with a single Latin letter.
# Small on purpose: only Latin, Cyrillic and Greek, only one-to-one letter pairs.
CONFUSABLE_TO_LATIN: dict[str, str] = {
    # Cyrillic lowercase
    "\u0430": "a", "\u0441": "c", "\u0435": "e", "\u04bb": "h", "\u0456": "i", "\u0458": "j",
    "\u043e": "o", "\u0440": "p", "\u0455": "s", "\u0445": "x", "\u0443": "y", "\u0501": "d",
    "\u051b": "q", "\u051d": "w",
    # Cyrillic uppercase
    "\u0410": "A", "\u0412": "B", "\u0421": "C", "\u0415": "E", "\u041d": "H", "\u0406": "I",
    "\u0408": "J", "\u041a": "K", "\u041c": "M", "\u041e": "O", "\u0420": "P", "\u0405": "S",
    "\u0422": "T", "\u0425": "X", "\u04ae": "Y", "\u051a": "Q", "\u051c": "W",
    # Greek
    "\u03bf": "o", "\u03bd": "v", "\u03b1": "a", "\u03b9": "i", "\u03c1": "p",
    "\u0391": "A", "\u0392": "B", "\u0395": "E", "\u0396": "Z", "\u0397": "H", "\u0399": "I",
    "\u039a": "K", "\u039c": "M", "\u039d": "N", "\u039f": "O", "\u03a1": "P", "\u03a4": "T",
    "\u03a5": "Y", "\u03a7": "X",
}  # fmt: skip
LATIN_TO_CONFUSABLE: dict[str, set[str]] = {}
for _k, _v in CONFUSABLE_TO_LATIN.items():
    LATIN_TO_CONFUSABLE.setdefault(_v, set()).add(_k)


def display(seq: str) -> str:
    """Readable form of a short sequence: invisible, control and space-like characters become <U+XXXX>."""
    out = []
    for ch in seq:
        cat = unicodedata.category(ch)
        if cat[0] == "C" or cat in ("Zs", "Zl", "Zp") and ch != " " or (cat == "Mn" and len(seq) == 1):
            out.append(f"<U+{ord(ch):04X}>")
        else:
            out.append(ch)
    return "".join(out)
