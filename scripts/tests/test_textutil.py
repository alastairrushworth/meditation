from textutil import (clean_description, is_placeholder_description, linkify,
                      sentence_list, slugify, strip_boilerplate, truncate_chars,
                      truncate_words)


def test_slugify():
    assert slugify("Ayya Anandabodhi") == "ayya-anandabodhi"
    assert slugify("Insight Meditation Society – Forest Refuge") == \
        "insight-meditation-society-forest-refuge"


def test_clean_description_strips_markup_and_entities():
    assert clean_description("<p>Hello &amp; welcome.</p>") == "Hello & welcome."


def test_strip_boilerplate_keeps_the_episode_specific_part():
    text = ("Settling into the breath and the body. Please consider supporting "
            "AudioDharma with a donation.")
    assert strip_boilerplate(text) == "Settling into the breath and the body."


def test_strip_boilerplate_drops_an_orphaned_lead_in():
    text = "Resting in awareness. Our introduction music is from X."
    assert strip_boilerplate(text) == "Resting in awareness."


def test_bracketed_centre_name_is_a_placeholder():
    # Several Dharma Seed sub-feeds publish exactly this as every description.
    assert is_placeholder_description("(Gaia House)")
    assert is_placeholder_description("(Insight Santa Cruz)")
    assert is_placeholder_description("")
    assert is_placeholder_description("Gaia House", "Gaia House")


def test_a_real_description_is_not_a_placeholder():
    assert not is_placeholder_description(
        "A settling practice working through the body from the feet upward.")


def test_truncate_words():
    assert truncate_words("one two three", 2) == "one two…"
    assert truncate_words("one two", 5) == "one two"


def test_truncate_chars_prefers_a_sentence_break():
    text = "A short first sentence here. And then a much longer second one that overruns."
    assert truncate_chars(text, 45) == "A short first sentence here."


def test_truncate_chars_falls_back_to_a_word_break():
    assert truncate_chars("supercalifragilistic expialidocious words", 25).endswith("…")


def test_linkify_leaves_trailing_punctuation_outside_the_link():
    out = linkify("See https://example.com/x.")
    assert 'href="https://example.com/x"' in out
    assert out.endswith(".")


def test_sentence_list():
    assert sentence_list(["a"]) == "a"
    assert sentence_list(["a", "b"]) == "a and b"
    assert sentence_list(["a", "b", "c"]) == "a, b and c"
    assert sentence_list([]) == ""


def test_leading_centre_name_is_stripped_from_a_real_description():
    text = "(Spirit Rock Meditation Center) Starting with a meditation on the natural world."
    assert clean_description(text, "Spirit Rock Meditation Center") == \
        "Starting with a meditation on the natural world."


def test_an_unrelated_bracketed_opening_is_left_alone():
    text = "(Part 2 of 3) A guided practice on the breath."
    assert clean_description(text, "Gaia House").startswith("(Part 2 of 3)")
