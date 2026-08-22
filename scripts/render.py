"""Turning archive records into pages.

Templates live in scripts/templates and are rendered with Jinja2 autoescaping,
so escaping is a property of the templating engine rather than something the
generator has to remember at each of a hundred interpolation points.
"""

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape as html_escape
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

import config
from classify import format_duration, iso_duration
from licence import attribution
from textutil import (indefinite_article, rich_description, sentence_list,
                      slugify, truncate_chars)

BASE_PATH = urlsplit(config.SITE_URL).path or "/"

LOTUS_PETAL = "M32 50 C27 42 27 27 32 15 C37 27 37 42 32 50Z"


def _lotus(css_class: str, opacity: str = "0.82") -> str:
    petals = "".join(
        f'<path d="{LOTUS_PETAL}" transform="rotate({angle} 32 50)"/>'
        for angle in (-75, -50, -25, 0, 25, 50, 75)
    )
    return Markup(
        f'<svg class="{css_class}" viewBox="0 0 64 64" aria-hidden="true" '
        f'focusable="false"><g fill="currentColor" fill-opacity="{opacity}" '
        f'style="color:var(--accent)">{petals}</g></svg>')


LOTUS = _lotus("brand-mark")


# --------------------------------------------------------------------------
# Assets
# --------------------------------------------------------------------------

def publish_assets() -> dict:
    """Copy CSS/JS into assets/ under a content-hashed name.

    A hashed filename lets the stylesheet be cached hard across all hundred-odd
    pages while still updating the moment it changes.
    """
    config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    published = {}
    static_dir = config.SCRIPTS_DIR / "static"

    for source in sorted(static_dir.glob("*")):
        if source.name.startswith("."):
            continue
        digest = hashlib.sha1(source.read_bytes()).hexdigest()[:10]
        target_name = f"{source.stem}.{digest}{source.suffix}"
        target = config.ASSETS_DIR / target_name
        if not target.exists():
            shutil.copy2(source, target)
        published[source.suffix.lstrip(".")] = target_name

    # Drop superseded builds so assets/ does not grow without bound.
    keep = set(published.values())
    for existing in config.ASSETS_DIR.glob("*"):
        if existing.name not in keep:
            existing.unlink()

    return published


# --------------------------------------------------------------------------
# View models
# --------------------------------------------------------------------------

PRACTICE_BY_SLUG = {p["slug"]: p for p in config.PRACTICES}
BUCKET_BY_SLUG = {b["slug"]: b for b in config.LENGTH_BUCKETS}


def _host(url: str) -> str:
    host = urlsplit(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _display_date(iso_date: str) -> str:
    """'2026-06-24' -> '24 June 2026'."""
    if not iso_date:
        return ""
    try:
        parsed = datetime.strptime(iso_date, "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{parsed.day} {parsed.strftime('%B %Y')}"


def compose_description(record: dict) -> str:
    """A sentence built from what we actually know about a recording.

    Several feeds publish nothing but the centre's name in brackets as the
    description. Rather than repeat the source label back at the reader, we
    write one honest line from the structured facts — and where there are no
    facts worth stating, we write nothing at all.
    """
    teacher = record.get("teacher")
    practices = record.get("practices") or []
    duration = format_duration(record.get("duration"))
    centre = record.get("feed_name")

    practice_word = ""
    if practices:
        practice_word = PRACTICE_BY_SLUG[practices[0]]["short"].lower()

    if not (teacher or practice_word):
        return ""

    if duration:
        length_phrase = f"{duration.replace(' min', '-minute').replace(' hr', '-hour')} "
    else:
        length_phrase = ""

    subject = f"{length_phrase}guided {practice_word} practice" if practice_word \
        else f"{length_phrase}guided practice"
    subject = re.sub(r"\s+", " ", subject).strip()
    article = indefinite_article(subject)

    sentence = f"{article.capitalize()} {subject}"
    if teacher:
        sentence += f" led by {teacher}"
    if centre and centre != teacher:
        sentence += f", from {centre}"
    return sentence + "."


def decorate(record: dict) -> dict:
    """Add everything a template needs that the archive does not store."""
    view = dict(record)
    duration = record.get("duration")

    view["date_display"] = _display_date(record.get("date"))
    view["duration_display"] = format_duration(duration)
    # Single-teacher podcasts are named after their teacher, so the card would
    # otherwise read "Tara Brach · Tara Brach", or the barely better
    # "Jack Kornfield · Heart Wisdom with Jack Kornfield".
    teacher = record.get("teacher") or ""
    feed_name = record.get("feed_name") or ""
    view["show_teacher"] = bool(teacher) and teacher.lower() not in feed_name.lower()

    if record.get("source_url"):
        view["link"] = record["source_url"]
        view["external"] = True
        view["source_host"] = _host(record["source_url"])
    else:
        # No episode page exists upstream — three podcasts publish none at all.
        # Rather than send a reader to a homepage from a named episode, the
        # recording gets a page here, with the audio and a link to the source.
        view["link"] = f"{BASE_PATH}listen/{record['slug']}/"
        view["external"] = False
        view["source_host"] = _host(record.get("feed_website"))

    description = record.get("description") or compose_description(record)
    view["description_html"] = Markup(rich_description(description, 90)) if description else ""
    view["description_plain"] = description

    view["practice_labels"] = [PRACTICE_BY_SLUG[s] for s in (record.get("practices") or [])
                               if s in PRACTICE_BY_SLUG][:3]
    view["licence"] = record.get("licence")
    view["attribution"] = attribution(record, record.get("licence"))
    view["player_sub"] = " · ".join(filter(None, [
        record["teacher"] if view["show_teacher"] else "", record.get("feed_name")]))
    view["search_text"] = " ".join(filter(None, [
        record.get("title", ""), record.get("teacher", ""), record.get("feed_name", ""),
    ])).lower()
    return view


# --------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------

def paginate(items: list, page_size: int, url_for) -> list:
    """Split items into page objects carrying their own navigation links."""
    total_pages = max(1, -(-len(items) // page_size))
    pages = []
    for number in range(1, total_pages + 1):
        start = (number - 1) * page_size
        window = items[start:start + page_size]

        if total_pages <= 9:
            numbers = list(range(1, total_pages + 1))
        elif number <= 4:
            numbers = [1, 2, 3, 4, 5, None, total_pages]
        elif number >= total_pages - 3:
            numbers = [1, None] + list(range(total_pages - 4, total_pages + 1))
        else:
            numbers = [1, None, number - 1, number, number + 1, None, total_pages]

        pages.append({
            "number": number,
            "total_pages": total_pages,
            "items": window,
            "start": start + 1,
            "end": start + len(window),
            "total_items": len(items),
            "url": url_for(number),
            "prev_url": url_for(number - 1) if number > 1 else None,
            "next_url": url_for(number + 1) if number < total_pages else None,
            "links": [{"ellipsis": True} if n is None else
                      {"number": n, "url": url_for(n), "current": n == number}
                      for n in numbers],
        })
    return pages


# --------------------------------------------------------------------------
# Structured data
# --------------------------------------------------------------------------

_ORIGIN = "{0.scheme}://{0.netloc}".format(urlsplit(config.SITE_URL))


def absolute(path_or_url: str) -> str:
    """Root-relative site path (or an already-absolute URL) to a full URL."""
    if not path_or_url:
        return ""
    if path_or_url.startswith("http"):
        return path_or_url
    return _ORIGIN + path_or_url


def episode_ld(view: dict) -> dict:
    """schema.org PodcastEpisode for one meditation.

    `url` is only ever a URL that actually shows this episode — the site's own
    page when the publisher offers none — so the markup never points three
    different episodes at one podcast homepage.
    """
    item = {
        "@type": "PodcastEpisode",
        "name": view["title"],
        "url": absolute(view["link"]),
        "partOfSeries": {"@type": "PodcastSeries", "name": view["feed_name"],
                         "url": view["feed_website"]},
    }
    if view.get("date"):
        item["datePublished"] = view["date"]
    if view.get("teacher"):
        item["author"] = {"@type": "Person", "name": view["teacher"]}
    if view.get("description_plain"):
        item["description"] = truncate_chars(view["description_plain"], 300)
    duration = iso_duration(view.get("duration"))
    if duration:
        item["timeRequired"] = duration
    if view.get("licence"):
        item["license"] = view["licence"]["url"]
        item["isAccessibleForFree"] = True
    if view.get("audio_url"):
        audio = {"@type": "AudioObject", "contentUrl": view["audio_url"]}
        if view.get("audio_type"):
            audio["encodingFormat"] = view["audio_type"]
        if duration:
            audio["duration"] = duration
        item["associatedMedia"] = audio
    return item


def website_ld() -> dict:
    return {
        "@type": "WebSite",
        "@id": config.SITE_URL + "#website",
        "name": config.SITE_NAME,
        "url": config.SITE_URL,
        "description": "A curated collection of guided meditations from dharma podcasts.",
        "inLanguage": config.LANG,
        "author": {"@type": "Person", "name": config.AUTHOR_NAME, "url": config.AUTHOR_URL},
        "publisher": {"@type": "Person", "name": config.AUTHOR_NAME},
    }


def breadcrumb_ld(crumbs: list) -> dict:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": c["label"],
             **({"item": absolute(c["url"])} if c.get("url") else {})}
            for i, c in enumerate(crumbs)
        ],
    }


def as_json_ld(payload: dict) -> Markup:
    """Serialise structured data for embedding in a <script> block.

    Marked safe because it is JSON, not HTML — but "</" is escaped first so a
    description containing "</script>" cannot close the block early.
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return Markup(text.replace("</", "<\\/"))


def collection_ld(url: str, name: str, description: str, views: list,
                  crumbs: list = None) -> str:
    graph = [website_ld()]
    page = {
        "@type": "CollectionPage",
        "@id": url + "#webpage",
        "url": url,
        "name": name,
        "description": description,
        "isPartOf": {"@id": config.SITE_URL + "#website"},
        "inLanguage": config.LANG,
        "mainEntity": {
            "@type": "ItemList",
            "itemListOrder": "https://schema.org/ItemListOrderDescending",
            "numberOfItems": len(views),
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "item": episode_ld(v)}
                for i, v in enumerate(views)
            ],
        },
    }
    graph.append(page)
    if crumbs:
        graph.append(breadcrumb_ld(crumbs))
    return as_json_ld({"@context": "https://schema.org", "@graph": graph})


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------

def build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(config.TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )
    env.filters["rfc822"] = lambda d: format_datetime(d) if d else ""
    env.filters["thousands"] = lambda n: f"{n:,}"
    return env


def nav_items(active: str) -> list:
    return [
        {"label": "Meditations", "href": BASE_PATH, "active": active == "home"},
        {"label": "About", "href": f"{BASE_PATH}about/", "active": active == "about"},
    ]


def base_context(assets: dict, **overrides) -> dict:
    context = {
        "base": BASE_PATH,
        "site_url": config.SITE_URL,
        "site_name": config.SITE_NAME,
        "subtitle": config.SITE_TAGLINE,
        "lang": config.LANG,
        "locale": config.LOCALE,
        "author_name": config.AUTHOR_NAME,
        "author_url": config.AUTHOR_URL,
        "repo_url": config.REPO_URL,
        "analytics": config.ANALYTICS if config.ANALYTICS.get("provider") else None,
        "css_file": assets.get("css", "site.css"),
        "js_file": assets.get("js", "site.js"),
        "lotus": LOTUS,
        "nav": nav_items(overrides.pop("active", "")),
        "is_home": False,
        "has_audio": True,
        "noindex": False,
        "prev_url": None,
        "next_url": None,
        "json_ld": None,
        "footer_line": "",
    }
    context.update(overrides)
    return context


def write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
