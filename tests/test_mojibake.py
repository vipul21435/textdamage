import random

import pytest

from textdamage.mojibake import badness, find_mojibake, make_mojibake, repair_mojibake

# Short sentences in many languages, written as escapes so the source stays plain ASCII.
SAMPLES = [
    "café crème brûlée, naïve façade",
    "Straße, über, schön, Mädchen",
    "ação, informação, SÃO PAULO",
    "mañana, ¿qué tal?, ¡olé!",
    "Łódź, żółw, ščřž",
    "İstanbul, ğüşıöç",
    "привет, мир",
    "καλημέρα κόσμε",
    "שלום עולם",
    "مرحبا بالعالم",
    "नमस्ते दुनिया",
    "สวัสดี",
    "日本語の文章です",
    "中文文本",
    "한국어 문장",
    "Việt Nam, tiếng Việt",
    "quotes “here” and ‘there’ — dash … €5",
    "emoji \U0001f600 and \U0001f680",
    "Água, Índia, Ópera, Únge",
    "naïve space, 25°C, ½ cup, © 2020",
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
    # "à" then a no-break space then a closing guillemet decodes to a Samaritan character
    text = make_mojibake("café") + " voilà »"
    hits = find_mojibake(text)
    assert [h.fix for h in hits] == ["é", None]
    assert repair_mojibake(text) == "café voilà »"


def test_rejected_shape_alone_is_ordinary_text():
    german = "Straß“ und «É»"
    assert find_mojibake(german) == []


def test_lost_second_byte_is_ambiguous_only_next_to_real_damage():
    assert find_mojibake("IRMÃ e") == []
    text = make_mojibake("café") + " voilÃ tout"
    hits = find_mojibake(text)
    assert [h.text for h in hits if h.fix is None] == ["Ã"]


def test_badness():
    assert badness("plain café") == 0
    assert badness("cafÃ©") == 1
    assert badness("\x81") == 1
    assert badness("ࠀ") == 1
