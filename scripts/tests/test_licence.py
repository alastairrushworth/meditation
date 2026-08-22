"""The licence gate decides whether a publisher's recordings may be used at all,
so its default must be 'no'."""

import pytest

from licence import detect_licence

DHARMA_SEED = ("Licensed under a Creative Commons Attribution-Noncommercial-"
               "NoDerivative Works 4.0 International License "
               "http://creativecommons.org/licenses/by-nc-nd/4.0/")
BSWA = ("Content on this site is licensed under a Creative Commons "
        "Attribution-NonCommercial-NoDerivs 3.0 Unported (CC BY-NC-ND 3.0)")


def test_recognises_the_dharma_seed_licence():
    assert detect_licence(DHARMA_SEED)["id"] == "cc-by-nc-nd-4.0"


def test_recognises_a_3_0_licence():
    assert detect_licence(BSWA)["id"] == "cc-by-nc-nd-3.0"


@pytest.mark.parametrize("text", [
    "Tara Brach - All rights reserved",
    "© Be Here Now Network",
    "All rights reserved",
    "Copyright 2022-2023, Everyday Zen Foundation",
])
def test_refuses_reserved_rights(text):
    assert detect_licence(text) is None


def test_refuses_silence():
    # No statement is not permission.
    assert detect_licence("") is None
    assert detect_licence(None) is None


def test_an_explicit_restriction_beats_a_licence_mention():
    assert detect_licence(
        "Creative Commons Attribution 4.0 — but these recordings may not be "
        "redistributed") is None


def test_reads_across_several_fields():
    assert detect_licence("", "some blurb",
                          "see http://creativecommons.org/licenses/by-nc-nd/4.0/"
                          )["id"] == "cc-by-nc-nd-4.0"
