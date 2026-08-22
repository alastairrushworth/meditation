#!/usr/bin/env python3
"""Build the Guided Meditations site from the archive.

    python3 scripts/generate.py            # fetch feeds, merge, rebuild
    python3 scripts/generate.py --no-fetch # rebuild pages from the archive only

The archive (data/meditations.json) is the source of truth. Feeds only ever add
to it, so a slow morning at one podcast host cannot remove content that search
engines have already indexed.
"""

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

import config
import render
import store
from classify import format_duration
from fetch import parse_feed
from render import BASE_PATH, absolute, base_context, decorate, paginate, write
from textutil import sentence_list, slugify, truncate_chars

BUILT = []          # (path, lastmod) for the sitemap


def log(message: str) -> None:
    print(message, flush=True)


def report_prune(archive: dict) -> None:
    """Say out loud what left the archive, and why it could."""
    pruned = archive.get("pruned") or {}
    if not pruned.get("count"):
        return
    log(f"\nRemoved {pruned['count']} recordings from podcasts no longer used:")
    for name, count in sorted(pruned["by_feed"].items(), key=lambda kv: -kv[1]):
        log(f"  − {name}: {count}")


# --------------------------------------------------------------------------
# Gathering
# --------------------------------------------------------------------------

def gather(feeds: list) -> tuple:
    """Fetch every feed, returning (results, records)."""
    results, records = [], []
    with requests.Session() as session:
        for feed_conf in feeds:
            result = parse_feed(feed_conf, session=session)
            results.append(result)
            if result.ok:
                records.extend(result.meditations)
                log(f"  {result.name}: {len(result.meditations)} meditations "
                    f"from {result.entries_seen} entries")
            elif result.licence_refused:
                # Not a failure — a decision. Logged distinctly so it is never
                # mistaken for an outage when reading a build.
                log(f"  {result.name}: LICENCE REFUSED — {result.error}; "
                    "its recordings will be removed")
            else:
                log(f"  {result.name}: FAILED — {result.error}")
    return results, records


# --------------------------------------------------------------------------
# Grouping
# --------------------------------------------------------------------------

def group_records(views: list) -> dict:
    """Index the collection by source centre, for the About page's list."""
    groups = {"feed": defaultdict(list)}
    for view in views:
        groups["feed"][view["feed_slug"]].append(view)
    return groups


# --------------------------------------------------------------------------
# Page builders
# --------------------------------------------------------------------------

def record_page(path: str, views: list) -> None:
    """Remember a page for the sitemap, with the newest item as its lastmod."""
    dates = [v.get("date") for v in views if v.get("date")]
    BUILT.append((path, max(dates) if dates else None))


# --------------------------------------------------------------------------
# Main build
# --------------------------------------------------------------------------

def build(views: list, feeds: list, archive: dict, assets: dict) -> None:
    env = render.build_env()
    groups = group_records(views)
    total = len(views)
    updated_display = datetime.now(timezone.utc).strftime("%d %B %Y").lstrip("0")

    feeds_by_slug = archive.get("feeds", {})
    sources = sorted(
        [{"slug": slug, "name": items[0]["feed_name"], "count": len(items)}
         for slug, items in groups["feed"].items()],
        key=lambda s: s["name"],
    )

    # --- Home: the archive itself, paginated ------------------------------
    # There is no separate "browse" page. One list, one place, with a single
    # compact filter row directly above it.
    teacher_counts_by_name = Counter(v["teacher"] for v in views if v["teacher"])
    top_teachers = sentence_list([t for t, _ in teacher_counts_by_name.most_common(3)])
    top_centres = sentence_list([s["name"] for s in
                                 sorted(sources, key=lambda x: -x["count"])[:4]])

    home_description = truncate_chars(
        f"{total:,} free guided meditations from {len(sources)} dharma and "
        "insight-meditation centres, all Creative Commons licensed"
        + (f", from teachers including {top_teachers}" if top_teachers else "")
        + ". Search by teacher, length or practice.", 158)

    def home_url(number: int) -> str:
        return BASE_PATH if number == 1 else f"{BASE_PATH}page/{number}/"

    for page in paginate(views, config.PAGE_SIZE, home_url):
        first = page["number"] == 1
        canonical = absolute(page["url"])
        title = (f"Guided Meditations — {total:,} free practices from dharma centres"
                 if first else
                 f"Guided meditations — page {page['number']} of {page['total_pages']}")
        html = env.get_template("home.html").render(**base_context(
            assets,
            active="home",
            is_home=True,
            page_title=title,
            page_description=(home_description if first else truncate_chars(
                f"Page {page['number']} of the archive: guided meditations "
                f"{page['start']}–{page['end']} of {total:,}, newest first.", 158)),
            canonical=canonical,
            meditations=page["items"],
            total_count=total,
            page=page,
            sources=sources,
            lengths=config.LENGTH_BUCKETS,
            practices=config.PRACTICES,
            footer_line=f"{total:,} meditations from {len(sources)} centres · "
                        f"last updated {updated_display}",
            prev_url=absolute(page["prev_url"]) if page["prev_url"] else None,
            next_url=absolute(page["next_url"]) if page["next_url"] else None,
            json_ld=render.collection_ld(canonical, title, home_description,
                                         page["items"]),
        ))
        write((config.SITE_ROOT if first
               else config.SITE_ROOT / "page" / str(page["number"])) / "index.html", html)
        record_page(page["url"], page["items"])

    # --- About: all the standing prose and the source list, in one place ---
    centres = []
    for slug, items in sorted(groups["feed"].items(), key=lambda kv: -len(kv[1])):
        meta = feeds_by_slug.get(slug, {})
        centres.append({
            "slug": slug, "name": items[0]["feed_name"], "count": len(items),
            "image": meta.get("image", ""), "website": items[0]["feed_website"],
            "licence": items[0].get("licence"),
        })
    licence_names = sentence_list(sorted({c["licence"]["name"] for c in centres
                                          if c.get("licence")}))
    about_canonical = absolute(f"{BASE_PATH}about/")

    html = env.get_template("about.html").render(**base_context(
        assets,
        active="about",
        page_title="About — how this collection is made",
        page_description=truncate_chars(
            f"How this collection of {total:,} free guided meditations is put "
            f"together, the {len(centres)} dharma centres it draws from, and the "
            "Creative Commons terms every recording is used under.", 158),
        canonical=about_canonical,
        has_audio=False,
        podcasts=centres,
        about_1=(
            "This is a hand-tended index of free guided meditations — the practices, "
            f"not the talks. A script reads the RSS feeds of {len(centres)} "
            "insight-meditation and dharma centres each week, keeps the episodes that "
            "are actually guided sittings, and files them by teacher, length and type "
            "of practice."),
        about_2=(
            "Nothing here is hosted or re-published. Audio streams from the original "
            "publisher and every title links to the centre's own page, so the centres "
            "keep their traffic and their attribution. The site carries no advertising "
            "and sells nothing."),
        about_3=(
            "The collection covers mindfulness and the body scan, breath and "
            "concentration practice, loving-kindness, compassion and equanimity, and "
            f"practices for difficult emotions — from teachers including {top_teachers}, "
            f"and from centres including {top_centres}."),
        about_licence_1=(
            "Every recording is published by its centre under a Creative Commons licence "
            "that permits non-commercial sharing of the unmodified talk with attribution "
            f"({licence_names}). Each is credited to its teacher and centre with a link "
            "to its licence, and the audio streams from the publisher's own servers "
            "rather than being copied here."),
        about_licence_2=(
            "The licence is read from each feed on every weekly build. A centre that "
            "stops declaring an open licence stops being used, and its recordings leave "
            "this site on the next run — which is why several well-known meditation "
            "podcasts that reserve their rights are not listed."),
        footer_line=f"{total:,} meditations from {len(centres)} centres",
        json_ld=render.as_json_ld({
            "@context": "https://schema.org",
            "@type": "AboutPage",
            "url": about_canonical,
            "name": "About this collection",
            "isPartOf": {"@id": config.SITE_URL + "#website"},
            "inLanguage": config.LANG,
            "mainEntity": {
                "@type": "ItemList",
                "name": "Source centres",
                "numberOfItems": len(centres),
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1,
                     "item": {k: v for k, v in {
                         "@type": "PodcastSeries", "name": c["name"],
                         "url": c["website"], "image": c["image"] or None,
                         "license": (c["licence"] or {}).get("url")}.items() if v}}
                    for i, c in enumerate(centres)
                ],
            },
        }),
    ))
    write(config.SITE_ROOT / "about" / "index.html", html)
    BUILT.append((f"{BASE_PATH}about/", None))

    # podcasts.html has been live and indexed since June, so the URL keeps
    # working rather than starting to 404.
    write(config.SITE_ROOT / "podcasts.html",
          env.get_template("redirect.html").render(
              lang=config.LANG, target=f"{BASE_PATH}about/",
              target_label="About this collection"))

    # --- Listen pages for episodes with no page upstream -------------------
    orphans = [v for v in views if not v["external"]]
    by_feed = defaultdict(list)
    for view in orphans:
        by_feed[view["feed_slug"]].append(view)

    for view in orphans:
        canonical = absolute(view["link"])
        siblings = [o for o in groups["feed"][view["feed_slug"]]
                    if o["id"] != view["id"]][:4]
        html = env.get_template("listen.html").render(**base_context(
            assets,
            active="",
            page_title=f"{view['title']} — {view['teacher'] or view['feed_name']}",
            page_description=truncate_chars(
                view["description_plain"] or
                f"A guided meditation from {view['feed_name']}"
                + (f", led by {view['teacher']}" if view["teacher"] else "") + ".", 158),
            canonical=canonical,
            m=view,
            more=siblings,
            has_audio=True,
            json_ld=render.as_json_ld({
                "@context": "https://schema.org",
                "@graph": [
                    render.episode_ld(view),
                    render.breadcrumb_ld([
                        {"label": "Meditations", "url": BASE_PATH},
                        {"label": view["title"], "url": None},
                    ]),
                ],
            }),
        ))
        write(config.SITE_ROOT / "listen" / view["slug"] / "index.html", html)
        BUILT.append((view["link"], view.get("date")))

    log(f"  listen pages: {len(orphans)} (episodes their podcast publishes no page for)")

    # --- Search index -----------------------------------------------------
    # Licences are shared by many recordings, so they are interned rather than
    # repeated 1,151 times — but every result still carries one, because
    # client-rendered search results need the same attribution as the page.
    licence_list, licence_index = [], {}
    for view in views:
        lic = view.get("licence")
        if lic and lic["id"] not in licence_index:
            licence_index[lic["id"]] = len(licence_list)
            licence_list.append({"n": lic["name"], "u": lic["url"]})

    index_items = [{
        "t": v["title"],
        "e": v["teacher"] if v["show_teacher"] else "",
        "n": v["feed_name"],
        "u": v["link"],
        "a": v.get("audio_url") or "",
        "d": v.get("duration_display") or "",
        "b": v.get("length_bucket") or "",
        "f": v["feed_slug"],
        "p": v.get("practices") or [],
        "l": licence_index.get((v.get("licence") or {}).get("id"), -1),
    } for v in views]
    write(config.SITE_ROOT / "search-index.json",
          json.dumps({"count": len(index_items), "licences": licence_list,
                      "items": index_items},
                     ensure_ascii=False, separators=(",", ":")))

    # --- RSS --------------------------------------------------------------
    feed_items = []
    for view in views[:config.FEED_ITEMS]:
        published = None
        if view.get("date"):
            published = datetime.strptime(view["date"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc)
        summary = view["description_plain"] or (
            f"A guided meditation from {view['feed_name']}"
            + (f", led by {view['teacher']}" if view["teacher"] else "") + ".")
        feed_items.append({
            "id": view["id"],
            "title_x": view["title"],
            "link_x": absolute(view["link"]),
            "summary_x": truncate_chars(summary, 400),
            "audio_url": view.get("audio_url"),
            "audio_url_x": view.get("audio_url"),
            "audio_type": view.get("audio_type"),
            "audio_bytes": view.get("audio_bytes"),
            "teacher": view.get("teacher"),
            "teacher_x": view.get("teacher"),
            "licence": view.get("licence"),
            "attribution": view.get("attribution"),
            "duration": format_duration(view.get("duration")),
            "rfc822": render.build_env().filters["rfc822"](published) if published else "",
        })

    write(config.SITE_ROOT / "feed.xml", env.get_template("feed.xml").render(
        site_name=config.SITE_NAME,
        site_url=config.SITE_URL,
        lang=config.LANG,
        repo_url=config.REPO_URL,
        author_name=config.AUTHOR_NAME,
        feed_copyright=(
            "Each recording remains the copyright of its teacher and centre, and is "
            "listed here under the Creative Commons licence its publisher applies. "
            "Audio is served by the original publisher."),
        feed_description=(
            "Guided meditations only — the practices, not the talks — curated weekly "
            f"from {len(sources)} insight-meditation and dharma podcasts."),
        build_date=render.build_env().filters["rfc822"](datetime.now(timezone.utc)),
        items=feed_items,
    ))

    # --- Sitemap ----------------------------------------------------------
    seen, urls = set(), []
    for path, lastmod in BUILT:
        loc = absolute(path)
        if loc in seen:
            continue
        seen.add(loc)
        urls.append({"loc": loc, "lastmod": lastmod})
    write(config.SITE_ROOT / "sitemap.xml",
          env.get_template("sitemap.xml").render(urls=urls))

    log(f"\n  pages: {len(urls)} | archive: {total} meditations")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def clean_generated() -> None:
    """Remove generated directories so renamed pages do not linger."""
    for name in ("all", "page", "lengths", "practices", "teachers", "podcasts",
                 "listen", "about"):   # legacy names included so they are cleared
        target = config.SITE_ROOT / name
        if target.is_dir():
            shutil.rmtree(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-fetch", action="store_true",
                        help="rebuild pages from the existing archive only")
    args = parser.parse_args()

    with config.FEEDS_FILE.open(encoding="utf-8") as handle:
        feeds = json.load(handle)["feeds"]

    archive = store.load_archive()
    log(f"Archive: {len(archive['meditations'])} meditations on disk")

    feed_results = []
    if args.no_fetch:
        log("Skipping fetch (--no-fetch); using archived feed metadata")
        archive = store.prune_removed_feeds(archive, {f["slug"] for f in feeds})
        report_prune(archive)
    else:
        log(f"Fetching {len(feeds)} feeds…")
        feed_results, records = gather(feeds)

        # Two kinds of removal, both deliberate: a podcast taken out of
        # feeds.json, and a podcast whose feed no longer declares a licence that
        # permits reuse. Either way its recordings leave the archive, and with
        # them its pages, feed items and search entries.
        refused = {r.slug for r in feed_results if r.licence_refused}
        keep = {f["slug"] for f in feeds} - refused
        archive = store.prune_removed_feeds(archive, keep)
        report_prune(archive)

        before = len(archive["meditations"])
        archive = store.merge(archive, records)
        archive = store.merge_feed_meta(archive, feed_results)
        after = len(archive["meditations"])
        try:
            store.guard_build(feed_results, before, after)
        except store.BuildAbandoned as exc:
            log(f"\nBUILD ABANDONED: {exc}")
            return 1
        log(f"\nMerged: +{archive['stats']['new']} new, "
            f"{archive['stats']['updated']} updated, "
            f"{archive['stats']['unchanged']} unchanged → {after} total")
        store.save_archive(archive)

    records = store.records_for_site(archive)
    if not records:
        log("BUILD ABANDONED: archive is empty")
        return 1

    views = [decorate(r) for r in records]

    assets = render.publish_assets()
    clean_generated()
    log("\nBuilding pages…")
    build(views, feeds, archive, assets)
    log("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
