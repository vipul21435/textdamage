"""Agreement with ftfy (test-only dependency) on cases where both should give the same answer."""

import random

import pytest

from tests.test_mojibake import SAMPLES
from textdamage.mojibake import make_mojibake, repair_mojibake

ftfy = pytest.importorskip("ftfy")


@pytest.mark.parametrize("clean", SAMPLES)
@pytest.mark.parametrize("rounds", [1, 2])
def test_same_repair_as_ftfy(clean, rounds):
    bad = make_mojibake(clean, "cp1252", rounds=rounds)
    assert repair_mojibake(bad) == clean
    assert ftfy.fix_encoding(bad) == clean


@pytest.mark.parametrize("clean", SAMPLES)
def test_both_leave_clean_text_alone(clean):
    assert repair_mojibake(clean) == clean
    assert ftfy.fix_encoding(clean) == clean


def test_agreement_on_random_word_mixtures():
    rng = random.Random(11)
    words = [w for s in SAMPLES for w in s.replace(",", " ").split()]
    agree = 0
    for _ in range(200):
        clean = " ".join(rng.sample(words, 4))
        bad = make_mojibake(clean)
        ours, theirs = repair_mojibake(bad), ftfy.fix_encoding(bad)
        assert ours == clean
        agree += ours == theirs
    assert agree >= 190
