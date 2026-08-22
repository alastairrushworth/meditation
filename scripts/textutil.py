"""Text cleaning: feed prose in, publishable prose out.

Feed descriptions arrive with markup, entity soup, per-episode donation pleas
and — on several feeds — nothing at all beyond the centre's name in brackets.
Everything here is a pure function so it can be tested without touching the
network.
"""

import re
import unicodedata
from html import escape as html_escape, unescape as html_unescape

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_tags(text: str) -> str:
    """Remove HTML tags, turning block boundaries into spaces."""
    if not text:
        return ""
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", " ", text)
    return _TAG_RE.sub("", text)


def slugify(value: str) -> str:
    """URL-safe slug: 'Ayya Anandabodhi' -> 'ayya-anandabodhi'."""
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value.strip("-")


# Boilerplate some feeds append to every episode: donation pleas, transcript
# notices, music credits. Repeated across a thousand cards it reads as templated
# filler to a reader and to a crawler. All of it trails the useful description,
# so we truncate at the first marker we recognise.
#
# Licence text is deliberately NOT in this list. These recordings are used under
# Creative Commons terms whose attribution clause requires the licence notice to
# travel with the work; stripping it as "boilerplate" would remove the very thing
# that makes the reuse permitted. It is rendered under each card instead.
_BOILERPLATE_MARKERS = (
    "video of this talk is available",
    "machine generated transcript",
    "machine-generated transcript",
    "download transcript",
    "for more talks",
    "if you have enjoyed this talk",
    "please consider supporting",
    "please support",
    "introduction music is from",
    "to support this podcast",
    "subscribe to this podcast",
    "see privacy policy",
    "see omnystudio.com",
    "learn more about your ad choices",
    "hosted on acast",
    "become a member",
    "donate to support",
)


def strip_boilerplate(text: str) -> str:
    """Drop trailing per-feed boilerplate, keeping the episode-specific intro."""
    if not text:
        return ""
    lowered = text.lower()
    cut = len(text)
    for marker in _BOILERPLATE_MARKERS:
        idx = lowered.find(marker)
        if idx != -1:
            cut = min(cut, idx)
    trimmed = text[:cut].strip()
    if cut < len(text):
        # The boilerplate began mid-sentence ("...mind. Our introduction music
        # is from..."). Drop a short orphaned lead-in left after the last
        # complete sentence, but never a real trailing sentence.
        last = max(trimmed.rfind("."), trimmed.rfind("!"), trimmed.rfind("?"))
        if last != -1 and len(trimmed[last + 1:].split()) <= 3:
            trimmed = trimmed[:last + 1]
    return trimmed


_LEADING_BRACKET_RE = re.compile(r"^\(([^)]{3,60})\)\s*")


def clean_description(description: str, feed_name: str = "") -> str:
    """Plain text with markup, entities, asterisk rules and boilerplate gone.

    Dharma Seed's sub-feeds prefix every description with the centre's name in
    brackets — sometimes as the whole description, sometimes ahead of real
    prose. The card already labels its source, so the prefix is dropped.
    """
    text = html_unescape(strip_tags(description or ""))
    text = re.sub(r"\*{3,}", "", text)
    text = re.sub(r"[-–—_]{4,}", " ", text)
    text = strip_boilerplate(text)
    text = _WS_RE.sub(" ", text).strip()
    match = _LEADING_BRACKET_RE.match(text)
    if match and (not feed_name or slugify(match.group(1)) == slugify(feed_name)):
        text = text[match.end():].strip()
    return text


# A description that is only the centre's name in brackets — "(Gaia House)" —
# carries nothing the card's own source label doesn't already say. Several
# Dharma Seed sub-feeds emit exactly this for every episode.
_BRACKETED_ONLY = re.compile(r"^\(.*\)$")
PLACEHOLDER_MIN_CHARS = 40


def is_placeholder_description(text: str, feed_name: str = "") -> bool:
    """True when a description carries no episode-specific information."""
    stripped = (text or "").strip()
    if not stripped:
        return True
    if _BRACKETED_ONLY.match(stripped):
        return True
    if feed_name and slugify(stripped) == slugify(feed_name):
        return True
    if len(stripped) < PLACEHOLDER_MIN_CHARS:
        return True
    return False


def truncate_words(text: str, limit: int) -> str:
    """Trim to at most `limit` words, appending an ellipsis when truncated."""
    words = (text or "").split()
    if len(words) > limit:
        return " ".join(words[:limit]).rstrip(",;:") + "…"
    return text or ""


def truncate_chars(text: str, limit: int) -> str:
    """Trim to `limit` characters, preferring a sentence break.

    Meta descriptions read badly when they stop mid-clause, so a full sentence
    that fits is always better than a longer fragment that does not.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    window = text[:limit]
    sentence_end = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if sentence_end >= limit * 0.6:
        return window[:sentence_end + 1]
    cut = window.rsplit(" ", 1)[0].rstrip(",;:.")
    return cut + "…"


_URL_RE = re.compile(r"(https?://[^\s<>\"{}|\\^`\[\]]+|www\.[^\s<>\"{}|\\^`\[\]]+)")


def linkify(escaped_text: str) -> str:
    """Turn bare URLs in already-escaped text into anchors."""
    def make_link(match):
        url = match.group(1)
        trailing = ""
        while url and url[-1] in ".,;:!?":
            trailing = url[-1] + trailing
            url = url[:-1]
        if not url:
            return match.group(1)
        href = url if url.startswith("http") else f"https://{url}"
        display = url if len(url) <= 48 else url[:45] + "…"
        return (f'<a href="{href}" rel="nofollow noopener noreferrer" '
                f'target="_blank">{display}</a>{trailing}')

    return _URL_RE.sub(make_link, escaped_text)


def rich_description(text: str, word_limit: int = 120) -> str:
    """Escaped, truncated, link-aware HTML for a card or page body."""
    return linkify(html_escape(truncate_words(text, word_limit)))


def sentence_list(items, conjunction: str = "and") -> str:
    """'a', 'a and b', 'a, b and c' — for prose built from data."""
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    return f"{', '.join(items[:-1])} {conjunction} {items[-1]}"


def indefinite_article(word: str) -> str:
    """'a' or 'an' for a following word — good enough for our vocabulary."""
    return "an" if word[:1].lower() in "aeiou" else "a"
