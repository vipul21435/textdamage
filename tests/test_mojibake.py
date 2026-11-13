import random

import pytest

from textdamage.mojibake import badness, find_mojibake, make_mojibake, repair_mojibake

# Short sentences in many languages, written as escapes so the source stays plain ASCII.
SAMPLES = [
    "caf\u00e9 cr\u00e8me br\u00fbl\u00e9e, na\u00efve fa\u00e7ade",
    "Stra\u00dfe, \u00fcber, sch\u00f6n, M\u00e4dchen",
    "a\u00e7\u00e3o, informa\u00e7\u00e3o, S\u00c3O PAULO",
    "ma\u00f1ana, \u00bfqu\u00e9 tal?, \u00a1ol\u00e9!",
    "\u0141\u00f3d\u017a, \u017c\u00f3\u0142w, \u0161\u010d\u0159\u017e",
    "\u0130stanbul, \u011f\u00fc\u015f\u0131\u00f6\u00e7",
    "\u043f\u0440\u0438\u0432\u0435\u0442, \u043c\u0438\u0440",
    "\u03ba\u03b1\u03bb\u03b7\u03bc\u03ad\u03c1\u03b1 \u03ba\u03cc\u03c3\u03bc\u03b5",
    "\u05e9\u05dc\u05d5\u05dd \u05e2\u05d5\u05dc\u05dd",
    "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645",
    "\u0928\u092e\u0938\u094d\u0924\u0947 \u0926\u0941\u0928\u093f\u092f\u093e",
    "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35",
    "\u65e5\u672c\u8a9e\u306e\u6587\u7ae0\u3067\u3059",
    "\u4e2d\u6587\u6587\u672c",
    "\ud55c\uad6d\uc5b4 \ubb38\uc7a5",
    "Vi\u1ec7t Nam, ti\u1ebfng Vi\u1ec7t",
    "quotes \u201chere\u201d and \u2018there\u2019 \u2014 dash \u2026 \u20ac5",
    "emoji \U0001f600 and \U0001f680",
    "\u00c1gua, \u00cdndia, \u00d3pera, \u00dange",
    "na\u00efve\u00a0space, 25\u00b0C, \u00bd cup, \u00a9 2020",
]


@pytest.mark.parametrize("clean", SAMPLES)
@pytest.mark.parametrize("encoding", ["cp1252", "latin-1"])
def test_one_round_is_found_and_repaired_exactly(clean, encoding):
    bad = make_mojibake(clean, encoding)
    assert bad != clean
    hits = find_mojibake(bad)
    assert hits and all(h.fix is not None and h.rounds == 1 for h in hits)
    assert repair_mojibake(bad) == clean


@pytest.mark.parametrize("clean", SAMPLES)
def test_two_rounds_are_found_and_repaired_exactly(clean):
    bad = make_mojibake(clean, "cp1252", rounds=2)
    assert repair_mojibake(bad) == clean
    assert any(h.rounds == 2 for h in find_mojibake(bad))


@pytest.mark.parametrize("clean", SAMPLES)
def test_clean_text_is_left_alone(clean):
    assert find_mojibake(clean) == []
    assert repair_mojibake(clean) == clean


def test_random_mixtures_property():
    rng = random.Random(7)
    for _ in range(300):
        parts = rng.sample(SAMPLES, 3)
        clean = " | ".join(parts)
        assert repair_mojibake(clean) == clean
        damaged_idx = rng.randrange(3)
        bad_parts = [make_mojibake(p) if i == damaged_idx else p for i, p in enumerate(parts)]
        bad = " | ".join(bad_parts)
        fixed = repair_mojibake(bad)
        # the damaged part is restored; clean parts written in non-Latin scripts are untouched
        assert parts[damaged_idx] in fixed


def test_ambiguous_is_counted_but_never_changed():
    # "\u00e0" then a no-break space then a closing guillemet decodes to a Samaritan character
    text = make_mojibake("caf\u00e9") + " voil\u00e0\u00a0\u00bb"
    hits = find_mojibake(text)
    assert [h.fix for h in hits] == ["\u00e9", None]
    assert repair_mojibake(text) == "caf\u00e9 voil\u00e0\u00a0\u00bb"


def test_rejected_shape_alone_is_ordinary_text():
    german = "Stra\u00df\u201c und \u00ab\u00c9\u00bb"
    assert find_mojibake(german) == []


def test_lost_second_byte_is_ambiguous_only_next_to_real_damage():
    assert find_mojibake("IRM\u00c3 e") == []
    text = make_mojibake("caf\u00e9") + " voil\u00c3 tout"
    hits = find_mojibake(text)
    assert [h.text for h in hits if h.fix is None] == ["\u00c3"]


def test_badness():
    assert badness("plain caf\u00e9") == 0
    assert badness("caf\u00c3\u00a9") == 1
    assert badness("\x81") == 1
    assert badness("\u0800") == 1


def test_script_clash_at_the_edge_is_refused():
    # Spanish capital I with acute before a closing guillemet decodes to a Greek letter
    assert repair_mojibake("\u00abAQU\u00cd\u00bb") == "\u00abAQU\u00cd\u00bb"
    # a Greek capital standing alone is still repaired
    assert repair_mojibake("letter \u00ce\u00a8 here") == "letter \u03a8 here"
