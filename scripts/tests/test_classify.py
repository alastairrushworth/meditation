"""The classifier decides what makes it onto the site, so it is the part most
worth pinning down: feeds change their titling conventions without warning."""

import pytest

from classify import (clean_title, classify_practices, extract_teacher,
                      format_duration, is_guided_meditation, iso_duration,
                      length_bucket, parse_duration,
                      teacher_from_description)


@pytest.mark.parametrize("title", [
    "Guided Meditation: Mudita Samadhi 3",
    "Meditation: Awakening an Intimate Presence",
    "Jill Shepherd: Meditation: Spacious awareness",
    "Mat Schencks: Guided Standing Meditation",
    "Body Scan for Deep Rest",
    "Guided Reflection on Impermanence",
])
def test_keeps_guided_practices(title):
    assert is_guided_meditation(title)


@pytest.mark.parametrize("title", [
    "Dharma Talk: The Second Arrow",
    "Dharmette: Gladness",
    "Q&A with Joseph Goldstein",
    "Ep. 37 – Questions On Loving Kindness",
    "A discussion of the five hindrances",
    "Interview with Sharon Salzberg",
    "",
])
def test_drops_talks_and_qa(title):
    assert not is_guided_meditation(title)


def test_explicit_practice_signal_survives_an_exclusion_word():
    # Half Q&A, half practice: the recording still contains a guided meditation,
    # so dropping it whole loses real content.
    assert is_guided_meditation(
        "Ep. 263 – The Certainty of Direct Experience: Q&A + Guided Practice")


def test_metta_alone_is_not_enough():
    assert not is_guided_meditation("The history of metta in the Pali canon")
    assert is_guided_meditation("Metta practice for a difficult person")


@pytest.mark.parametrize("raw,teacher,rest", [
    ("Jill Shepherd: Meditation: Spacious awareness", "Jill Shepherd", "Meditation: Spacious awareness"),
    ("Ayya Anandabodhi: Guided Meditation on the Brahmaviharas", "Ayya Anandabodhi", "Guided Meditation on the Brahmaviharas"),
    ("2026 June | 5 Day Retreat (12/12)| Ayya Karunika", "Ayya Karunika", "2026 June | 5 Day Retreat (12/12)"),
])
def test_extracts_the_teacher(raw, teacher, rest):
    assert extract_teacher(raw) == (teacher, rest)


@pytest.mark.parametrize("raw", [
    "Guided Meditation: Mudita Samadhi 3",   # format label, not a name
    "Meditation: Being Here",
    "180 - Meditation: The Pause Button",
])
def test_does_not_invent_a_teacher(raw):
    assert extract_teacher(raw)[0] == ""


def test_feed_default_teacher_only_fills_a_gap():
    assert extract_teacher("Meditation: Being Here", "Tara Brach")[0] == "Tara Brach"
    assert extract_teacher("Jean Esther: Guided Equanimity", "Tara Brach")[0] == "Jean Esther"


@pytest.mark.parametrize("raw,expected", [
    ("Meditation: Living Presence (2016-03-23) (20:01 min)", "Meditation: Living Presence"),
    ("2015-02-18 - Part 2: Basic Elements", "Part 2: Basic Elements"),
    ("Ep. 320 – Guided Meditation for Grounding", "Guided Meditation for Grounding"),
    ("11 meditation: Exploring cetana", "Meditation: Exploring cetana"),
    ("Meditation: Mindful Body Scan (10:06 min.)", "Meditation: Mindful Body Scan"),
])
def test_cleans_titles(raw, expected):
    assert clean_title(raw) == expected


def test_practice_classification_prefers_the_title():
    assert classify_practices("Guided Body Scan")[0] == "body-scan"
    assert "loving-kindness" in classify_practices("Metta for a difficult person")


def test_practice_keywords_respect_word_boundaries():
    # "pain" must not match "painting"; the old substring match did.
    assert "difficult-emotions" not in classify_practices("Meditation on painting")
    assert "difficult-emotions" in classify_practices("Meditation for pain")


@pytest.mark.parametrize("raw,seconds", [
    ("01:02:03", 3723), ("21:30", 1290), ("1260", 1260), ("", None),
    (None, None), ("banana", None), ("0", None), ("99:00:00", None),
])
def test_parses_durations(raw, seconds):
    assert parse_duration(raw) == seconds


def test_formats_durations():
    assert format_duration(1290) == "22 min"
    assert format_duration(5280) == "1 hr 28 min"
    assert format_duration(3600) == "1 hr"
    assert format_duration(None) is None


def test_iso_durations():
    assert iso_duration(1290) == "PT21M30S"
    assert iso_duration(None) is None


def test_length_buckets_follow_the_round_numbers():
    assert length_bucket(9 * 60) == "10-minutes"
    assert length_bucket(20 * 60) == "20-minutes"
    assert length_bucket(90 * 60) == "60-minutes"
    assert length_bucket(None) is None


def test_recovers_a_teacher_named_only_in_the_description():
    # AudioDharma never puts the teacher in the title.
    assert teacher_from_description(
        "This talk was given by Gil Fronsdal on 2026.08.21 at IMC.") == "Gil Fronsdal"
    assert teacher_from_description("A guided sitting.") == ""
