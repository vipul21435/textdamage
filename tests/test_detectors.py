from collections import Counter

import pytest

from textdamage.detectors import CLASSES, scan_text


def counts(text, **kw):
    return Counter(f.cls for f in scan_text(text, **kw))


def test_clean_ascii_has_no_findings():
    assert scan_text("A plain sentence, with punctuation; and digits 123.") == []


@pytest.mark.parametrize(
    "text,cls,n",
    [
        ("bad \ufffd and \ufffd", "replacement", 2),
        ("nul\x00 and bell\x07 tab\tok\n", "c0", 2),
        ("a\x85b\x9fc", "c1", 2),
        ("zero\u200bwidth\u2060join\u00ad", "invisible", 3),
        ("abc\u202eedc\u202c and \u2066x\u2069", "bidi", 4),
        ("mid\ufefftext", "bom", 1),
        ("cafe\u0301 and nai\u0308ve", "non-nfc", 2),
        ("\uff21\uff22 and \U0001d400 and \ufb01", "compat", 4),
        ("p\u0430ypal and g\u043e\u043egle", "confusable", 2),
        ("line one\\nLine two\\u00e9 and \\x41", "escape", 3),
        ("fish &amp; chips &#233; &#xE9; &notanentity;", "entity", 3),
        ("x\ud800y\udc80", "surrogate", 2),
    ],
)
def test_detector_counts(text, cls, n):
    assert counts(text)[cls] == n


def test_legitimate_joiners_are_not_counted():
    family = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
    heart = "\u2764\ufe0f"
    persian = "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645"
    flag = "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f"
    for text in (family, heart, persian, flag):
        assert counts(text)["invisible"] == 0, text
    assert counts("ab\u200dcd")["invisible"] == 1


def test_latex_and_code_are_not_escapes():
    assert counts("the angle \\theta and \\newline")["escape"] == 0
    assert counts("use `print('a\\n')` here")["escape"] == 0
    assert counts("```\nx = '\\u00e9'\n```")["escape"] == 0
    assert counts("```\nx = '&amp;'\n```")["entity"] == 0


def test_repeats():
    assert counts("wait" + " " * 12 + "here")["repeat"] == 1
    assert counts("    indented code line")["repeat"] == 0
    assert counts("so good!!!!!!!!!!!!")["repeat"] == 1
    assert counts("title\n" + "=" * 20 + "\nbody")["repeat"] == 0
    assert counts("| a | b |\n|" + "-" * 12 + "|" + "-" * 12 + "|")["repeat"] == 0
    assert counts("a" + "\n" * 12 + "b")["repeat"] == 1
    assert counts("so good!!!!", repeat_min=4)["repeat"] == 1
    with pytest.raises(ValueError):
        scan_text("x", repeat_min=1)


def test_confusable_cyrillic_majority():
    # Cyrillic word with one Latin "o" inside
    assert counts("\u043fo\u0440\u0442")["confusable"] == 1
    # a Greek word on its own is fine
    assert counts("\u03b1\u03bb\u03c6\u03b1")["confusable"] == 0


def test_ignore_list_drops_accepted_characters():
    assert counts("a\u200bb", ignore={"\u200b"})["invisible"] == 0
    assert counts("a\u200bb\u2060", ignore={"\u200b"})["invisible"] == 1


def test_class_filter_and_unknown_class():
    text = "x\u200by\ufffd"
    assert set(counts(text, classes=["invisible"])) == {"invisible"}
    with pytest.raises(ValueError):
        scan_text("x", classes=["nope"])


def test_class_list_is_stable():
    assert CLASSES[0] == "mojibake" and len(set(CLASSES)) == len(CLASSES)


def test_fullwidth_punctuation_is_not_compat():
    assert counts("\u4f60\u597d\uff0c\u4e16\u754c\uff1f")["compat"] == 0
    assert counts("\uff21\uff11")["compat"] == 2


def test_repeats_inside_code_are_skipped():
    code = "```\nx = 1" + " " * 12 + "# aligned\n```"
    assert counts(code)["repeat"] == 0
