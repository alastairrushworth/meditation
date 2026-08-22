"""Fetching and normalising podcast feeds.

Network failures are reported, never swallowed: a feed that cannot be read
returns a FeedResult marked failed, and the caller decides whether the build is
still worth publishing (see store.guard_build).
"""

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import feedparser
import requests

from classify import (classify_practices, clean_title, extract_teacher,
                      is_guided_meditation, length_bucket, parse_duration,
                      teacher_from_description)
from config import (FETCH_BACKOFF, FETCH_RETRIES, FETCH_TIMEOUT, USER_AGENT)
from licence import detect_licence
from textutil import (clean_description, is_placeholder_description, slugify)

DHARMASEED_LOGO = "https://media.dharmaseed.org/images/DS-rss-logo.jpg"


@dataclass
class FeedResult:
    """Everything one feed contributed to a build, including how it went."""
    name: str
    slug: str
    website: str
    ok: bool = False
    licence_refused: bool = False
    error: str = ""
    image: str = ""
    description: str = ""
    licence: dict = None
    entries_seen: int = 0
    meditations: list = field(default_factory=list)


def _canonical_url(url: str) -> str:
    """Normalise a URL for identity comparison: scheme, host case, trailing slash."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme in ("http", "https", "") else parts.scheme
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def _is_episode_specific(url: str, feed_website: str) -> bool:
    """False when a 'link' is really just the podcast's front page.

    Three feeds publish no per-episode link at all, and a couple more fall back
    to their own homepage. Sending a reader to a homepage from a named episode
    is a broken promise, so those are routed to a page on this site instead.
    """
    if not url or not url.lower().startswith("http"):
        return False
    canonical = _canonical_url(url)
    if canonical == _canonical_url(feed_website):
        return False
    # A bare domain with no path is a front page whichever feed it came from.
    return urlsplit(canonical).path not in ("", "/")


def _pick_audio(entry) -> tuple:
    """(url, mime type, byte length) of the episode's audio enclosure."""
    for enclosure in (entry.get("enclosures") or []):
        href = enclosure.get("href") or enclosure.get("url") or ""
        mime = enclosure.get("type") or ""
        if href and (mime.startswith("audio") or href.lower().endswith(
                (".mp3", ".m4a", ".aac", ".ogg", ".wav"))):
            try:
                length = int(enclosure.get("length") or 0) or None
            except (TypeError, ValueError):
                length = None
            return href, mime or "audio/mpeg", length
    for link in (entry.get("links") or []):
        if (link.get("rel") == "enclosure") and link.get("href"):
            return link["href"], link.get("type") or "audio/mpeg", None
    return "", "", None


def _entry_date(entry):
    """Published date as an aware UTC datetime, or None when the feed omits it.

    Never substitute 'now': an undated recording stamped with today's date sorts
    to the top of the site and presents an unknown-age talk as the newest thing
    on it.
    """
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _record_id(source_url: str, audio_url: str, guid: str, title: str) -> str:
    """Stable identity for an episode across builds and across feeds.

    Keyed on the episode's own page where there is one, then its audio file,
    then its GUID — so the same recording surfaced by two feeds (Dharma Seed
    republishes every centre's talks) resolves to one record.
    """
    for candidate in (_canonical_url(source_url), _canonical_url(audio_url), guid, title):
        if candidate:
            return hashlib.sha1(candidate.encode("utf-8")).hexdigest()[:16]
    return ""


def _episode_slug(title: str, teacher: str, record_id: str) -> str:
    """Readable, unique-enough slug for episodes that need a page here."""
    stem = slugify(f"{teacher} {title}")[:70].strip("-") or "meditation"
    return f"{stem}-{record_id[:6]}"


def extract_feed_meta(parsed, feed_conf: dict) -> tuple:
    """Channel artwork, blurb and licence for the podcasts pages."""
    channel = getattr(parsed, "feed", {}) or {}

    image = ""
    raw_image = channel.get("image")
    if isinstance(raw_image, dict):
        image = raw_image.get("href") or raw_image.get("url") or ""
    if not image:
        itunes_image = channel.get("itunes_image")
        if isinstance(itunes_image, dict):
            image = itunes_image.get("href") or itunes_image.get("url") or ""
    # Dharma Seed's per-centre sub-feeds carry no artwork of their own.
    if not image and "dharmaseed.org" in feed_conf["url"].lower():
        image = DHARMASEED_LOGO

    blurb = (channel.get("subtitle") or channel.get("summary")
             or channel.get("description") or "")

    # Read the terms from the feed itself on every build, so a publisher who
    # changes them is honoured on the next run rather than whenever noticed.
    licence = detect_licence(channel.get("rights"), channel.get("copyright"),
                             channel.get("license"), channel.get("creativecommons_license"))
    return image, clean_description(blurb, feed_conf["name"]), licence


def parse_feed(feed_conf: dict, session=None) -> FeedResult:
    """Fetch one feed and return its guided meditations, or why it failed."""
    result = FeedResult(name=feed_conf["name"], slug=feed_conf["slug"],
                        website=feed_conf["website"])
    session = session or requests
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"}

    last_error = ""
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            response = session.get(feed_conf["url"], headers=headers, timeout=FETCH_TIMEOUT)
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
            if not parsed.entries and getattr(parsed, "bozo", 0):
                raise ValueError(f"unparseable feed: {getattr(parsed, 'bozo_exception', '')}")
            break
        except Exception as exc:                      # noqa: BLE001 - reported, not swallowed
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < FETCH_RETRIES:
                time.sleep(FETCH_BACKOFF * attempt)
    else:
        result.error = last_error
        return result

    result.ok = True
    result.image, result.description, result.licence = extract_feed_meta(parsed, feed_conf)

    # No recognised open licence means no permission to stream the audio or
    # reproduce the descriptions, so the feed contributes nothing at all.
    if not result.licence:
        # ok stays False: nothing from this feed may be used. It is flagged
        # separately from a fetch failure so the build guard does not treat a
        # withdrawn licence as an outage, and so the stored artwork and blurb
        # are not refreshed for a publisher we are no longer listing.
        result.ok = False
        result.licence_refused = True
        result.error = "no open licence declared in the feed"
        result.entries_seen = len(parsed.entries)
        return result
    result.entries_seen = len(parsed.entries)

    default_teacher = feed_conf.get("teacher", "")
    for entry in parsed.entries:
        raw_title = (entry.get("title") or "").strip()
        if not is_guided_meditation(raw_title):
            continue

        teacher, remainder = extract_teacher(raw_title, default_teacher)
        title = clean_title(remainder)
        if not title:
            continue

        raw_description = entry.get("description") or entry.get("summary") or ""
        description = clean_description(raw_description, feed_conf["name"])
        if not teacher:
            teacher = teacher_from_description(description)
        if is_placeholder_description(description, feed_conf["name"]):
            description = ""

        audio_url, audio_type, audio_bytes = _pick_audio(entry)
        link = entry.get("link") or ""
        guid = entry.get("id") or ""
        source_url = ""
        if _is_episode_specific(link, feed_conf["website"]):
            source_url = link
        elif _is_episode_specific(guid, feed_conf["website"]):
            source_url = guid

        record_id = _record_id(source_url, audio_url, guid, raw_title)
        if not record_id:
            continue

        published = _entry_date(entry)
        duration = parse_duration(entry.get("itunes_duration"))

        result.meditations.append({
            "id": record_id,
            "slug": _episode_slug(title, teacher, record_id),
            "title": title,
            "title_raw": raw_title,
            "teacher": teacher,
            "teacher_slug": slugify(teacher) if teacher else "",
            "description": description,
            "date": published.strftime("%Y-%m-%d") if published else None,
            "source_url": source_url,
            "audio_url": audio_url,
            "audio_type": audio_type,
            "audio_bytes": audio_bytes,
            "duration": duration,
            "length_bucket": length_bucket(duration),
            "practices": classify_practices(title, description),
            "feed_name": feed_conf["name"],
            "feed_slug": feed_conf["slug"],
            "feed_website": feed_conf["website"],
            "from_aggregator": bool(feed_conf.get("aggregator")),
            "licence": result.licence,
        })

    return result
