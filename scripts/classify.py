"""Deciding what an episode *is*: meditation or talk, whose, and what practice.

The classifier reads titles rather than descriptions. Many dharma talks mention
"guided meditation" in their show notes, so matching descriptions floods the
collection with talks and Q&As; titles are both more precise and, because of
conventions like "Meditation: Body Scan", more thorough.
"""

import re

from config import LENGTH_BUCKETS, PRACTICES
from textutil import slugify

# --- Is it a guided meditation? -------------------------------------------

# Signals that an episode is a guided practice.
MEDITATION_KEYWORDS = [
    "meditation",
    "body scan",
    "guided ",
]

# Practice vocabulary that only counts when paired with a practice word: a talk
# titled "Questions On Loving Kindness" is about metta, not a metta practice.
QUALIFIED_KEYWORDS = ["metta", "loving-kindness", "loving kindness", "brahmavihara"]
QUALIFIERS = ["practice", "meditation", "guided", "instruction", "sit "]

# Formats that are talks rather than practices.
EXCLUDE_KEYWORDS = [
    "dharmette",
    "practice notes",
    "dharma talk",
    "questions and answers",
    "q&a",
    "q & a",
    "discussion",
    "interview",
    "book club",
    "panel",
    "questions on",
    "questions about",
    "questions &",
    "answering questions",
]

# An explicit practice signal outranks an exclusion signal. Several podcasts
# publish episodes titled "... : Q&A + Guided Practice" — dropping those whole
# loses a real guided meditation because the same recording also answers
# questions. Inclusion wins; the exclusions still catch pure talks.
STRONG_MEDITATION_SIGNALS = [
    "guided meditation",
    "guided practice",
    "guided reflection",
    "guided metta",
    "guided relaxation",
    "meditation:",
    "body scan",
]


def has_strong_signal(title: str) -> bool:
    """True when the title explicitly announces a guided practice."""
    lowered = (title or "").lower()
    return any(signal in lowered for signal in STRONG_MEDITATION_SIGNALS)


def is_guided_meditation(title: str) -> bool:
    """Classify an episode from its title alone."""
    lowered = (title or "").lower()
    if not lowered.strip():
        return False
    excluded = any(word in lowered for word in EXCLUDE_KEYWORDS)
    if excluded and not has_strong_signal(title):
        return False
    if any(keyword in lowered for keyword in MEDITATION_KEYWORDS):
        return True
    if any(keyword in lowered for keyword in QUALIFIED_KEYWORDS):
        return any(qualifier in lowered for qualifier in QUALIFIERS)
    return False


# --- Who taught it? --------------------------------------------------------

# Words that disqualify a colon-prefix from being read as a person's name.
_NOT_A_NAME = {
    "meditation", "meditations", "guided", "practice", "practices", "dharma",
    "talk", "talks", "retreat", "day", "days", "week", "morning", "evening",
    "afternoon", "night", "part", "session", "intro", "introduction", "series",
    "instruction", "instructions", "reflection", "episode", "ep", "class",
    "course", "q&a", "qa", "week", "chapter", "study", "the", "a", "an",
    "sunday", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
}

# A name token: capitalised, possibly with an apostrophe, hyphen or full stop
# (Ajahn, Ayya, Rev., O'Brien, Thanissara-Mary).
_NAME_TOKEN = r"[A-Z][A-Za-z'’.\-]*"
_TEACHER_PREFIX_RE = re.compile(rf"^({_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}}):\s+(.+)$")
_TEACHER_SUFFIX_RE = re.compile(rf"\|\s*({_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}})\s*$")


def _looks_like_person(candidate: str) -> bool:
    """Reject 'Guided Meditation' and 'June 2026' while accepting 'Ayya Karunika'."""
    words = candidate.split()
    if not 1 < len(words) <= 4:
        # Single-word prefixes are almost always a format label, not a name.
        return False
    if len(candidate) > 42:
        return False
    if any(word.lower().strip(".") in _NOT_A_NAME for word in words):
        return False
    if any(char.isdigit() for char in candidate):
        return False
    return True


def extract_teacher(title: str, default_teacher: str = "") -> tuple:
    """Split a teacher's name off the title.

    Returns (teacher, remaining_title). Dharma Seed titles the teacher as a
    colon prefix; the Ajahn Brahm feed appends it after a pipe. A feed-level
    default (single-teacher podcasts) is used only when the title names nobody.
    """
    title = (title or "").strip()

    match = _TEACHER_PREFIX_RE.match(title)
    if match and _looks_like_person(match.group(1)):
        return match.group(1).strip(), match.group(2).strip()

    match = _TEACHER_SUFFIX_RE.search(title)
    if match and _looks_like_person(match.group(1)):
        return match.group(1).strip(), title[: match.start()].strip(" |-–—")

    return (default_teacher or "").strip(), title


# AudioDharma names the teacher only in the description ("This talk was given
# by Gil Fronsdal on 2026.08.21 at ..."), so 36 recordings would otherwise sit
# in the archive with no teacher and no teacher page.
# The lead-in is case-insensitive; the name is not. A global IGNORECASE flag
# would make _NAME_TOKEN's [A-Z] match lowercase words and swallow "... on".
_TEACHER_IN_BODY_RE = re.compile(
    rf"(?i:\b(?:talk|meditation|recording)?\s*was given by\s+)"
    rf"({_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}})\b")


def teacher_from_description(description: str) -> str:
    """Teacher named in the body text rather than the title."""
    match = _TEACHER_IN_BODY_RE.search(description or "")
    if match and _looks_like_person(match.group(1)):
        return match.group(1).strip()
    return ""


# --- Cleaning the title ----------------------------------------------------

# "Meditation: Being Here (21:22 min.)" — the running time is already shown in
# the card's meta row, so repeating it in the heading is noise.
_TRAILING_DURATION_RE = re.compile(
    r"\s*[\(\[]\s*\d{1,3}\s*[:.]?\s*\d{0,2}\s*(?:min|mins|minutes|m)?\.?\s*[\)\]]\s*$",
    re.IGNORECASE,
)
_LEADING_EPISODE_RE = re.compile(r"^(?:ep|episode|no)\.?\s*\d+\s*[-–—:]?\s*", re.IGNORECASE)
# Tara Brach's feed stamps the recording date into the title, at either end.
_TRAILING_DATE_RE = re.compile(r"\s*[\(\[]\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*[\)\]]\s*$")
_LEADING_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*[-–—:]?\s*")
# A bare leading talk number, but only when what follows is not itself a count
# ("5 Day Retreat" keeps its 5; "32 meditation: ..." loses its 32).
_LEADING_NUMBER_RE = re.compile(r"^\d{1,4}\s*[-–—:.]\s+|^\d{1,4}\s+(?=[a-z])")


def clean_title(title: str) -> str:
    """Normalise a feed title into a usable heading."""
    title = re.sub(r"\s+", " ", (title or "").strip())
    title = _LEADING_DATE_RE.sub("", title)
    title = _LEADING_EPISODE_RE.sub("", title)
    title = _LEADING_NUMBER_RE.sub("", title)
    previous = None
    while previous != title:            # titles often carry a date *and* a time
        previous = title
        title = _TRAILING_DURATION_RE.sub("", title).strip()
        title = _TRAILING_DATE_RE.sub("", title).strip()
    title = title.strip(" -–—:|")
    title = re.sub(r"\s*\|\s*", " | ", title)
    title = re.sub(r"\s+", " ", title).strip()
    if title and title[0].islower():
        title = title[0].upper() + title[1:]
    return title


# --- What practice is it? --------------------------------------------------

_KEYWORD_RES = {}


def _keyword_re(keyword: str):
    """Cached whole-word matcher — 'pain' must not match 'painting'."""
    if keyword not in _KEYWORD_RES:
        term = keyword.strip()
        trailing = r"\b" if term[-1:].isalnum() else ""
        _KEYWORD_RES[keyword] = re.compile(rf"\b{re.escape(term)}{trailing}",
                                           re.IGNORECASE)
    return _KEYWORD_RES[keyword]


def classify_practices(title: str, description: str = "") -> list:
    """Practice slugs this episode belongs to, most specific first.

    The title is weighted far more heavily than the description: a talk that
    merely mentions equanimity should not land in the equanimity collection.
    """
    title_lower = (title or "").lower()
    body_lower = f"{title_lower} {(description or '').lower()[:400]}"
    found = []
    for practice in PRACTICES:
        in_title = any(_keyword_re(k).search(title_lower) for k in practice["keywords"])
        in_body = any(_keyword_re(k).search(body_lower) for k in practice["keywords"])
        if in_title or in_body:
            found.append((0 if in_title else 1, practice["slug"]))
    found.sort()
    return [slug for _, slug in found]


# --- How long is it? -------------------------------------------------------

def parse_duration(raw) -> int:
    """Feed duration (HH:MM:SS, MM:SS or bare seconds) to whole seconds."""
    if raw in (None, "", False):
        return None
    text = str(raw).strip()
    try:
        if ":" in text:
            parts = [int(float(p)) for p in text.split(":")]
            if len(parts) == 3:
                hours, minutes, seconds = parts
            elif len(parts) == 2:
                hours, minutes, seconds = 0, parts[0], parts[1]
            else:
                return None
            total = hours * 3600 + minutes * 60 + seconds
        else:
            total = int(float(text))
    except (ValueError, TypeError):
        return None
    # Guard against nonsense: a "duration" of 0 or over 12 hours is bad data.
    if total <= 0 or total > 12 * 3600:
        return None
    return total


def format_duration(seconds) -> str:
    """Seconds to a human label: '21 min', '1 hr 28 min'. None when unknown."""
    if not seconds:
        return None
    hours, minutes = divmod(round(seconds / 60), 60)
    if hours:
        return f"{hours} hr {minutes} min" if minutes else f"{hours} hr"
    return f"{minutes} min"


def iso_duration(seconds) -> str:
    """Seconds to an ISO 8601 duration for schema.org."""
    if not seconds:
        return None
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    out = "PT"
    if hours:
        out += f"{hours}H"
    if minutes:
        out += f"{minutes}M"
    if secs:
        out += f"{secs}S"
    return out if out != "PT" else None


def length_bucket(seconds) -> str:
    """Slug of the length collection this duration belongs in."""
    if not seconds:
        return None
    for bucket in LENGTH_BUCKETS:
        if bucket["max_seconds"] is None or seconds <= bucket["max_seconds"]:
            return bucket["slug"]
    return LENGTH_BUCKETS[-1]["slug"]
