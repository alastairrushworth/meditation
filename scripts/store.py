"""The archive: the site's memory.

Before this existed the generator rebuilt the page from whatever the feeds
happened to return that morning and overwrote everything else, so the site
never grew past a couple of dozen items and any episode search engines had
indexed was gone within a week. The archive is now the source of truth; feeds
only ever *add* to it.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from config import ARCHIVE_FILE, MAX_FAILED_FEED_FRACTION

SCHEMA_VERSION = 1

# Fields a later build may improve on an existing record. A value already held
# is only replaced by a better one — never by an empty one, so a feed that
# temporarily drops its descriptions cannot hollow out the archive.
_UPGRADEABLE = ("title", "teacher", "teacher_slug", "description", "date",
                "source_url", "audio_url", "audio_type", "audio_bytes",
                "duration", "length_bucket", "practices", "slug", "title_raw",
                "licence")


class BuildAbandoned(Exception):
    """Raised when a build is too degraded to publish."""


def load_archive(path: Path = ARCHIVE_FILE) -> dict:
    """Read the archive, returning an empty one when it does not yet exist."""
    if not path.exists():
        return {"version": SCHEMA_VERSION, "updated": None,
                "meditations": {}, "feeds": {}}
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload.get("meditations", [])
    if isinstance(records, list):
        records = {record["id"]: record for record in records if record.get("id")}
    return {"version": payload.get("version", SCHEMA_VERSION),
            "updated": payload.get("updated"),
            "meditations": records,
            "feeds": payload.get("feeds", {})}


def save_archive(archive: dict, path: Path = ARCHIVE_FILE) -> None:
    """Write the archive as a stable, diff-friendly list."""
    path.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(archive["meditations"].values(),
                     key=lambda r: (r.get("date") or "", r.get("id", "")),
                     reverse=True)
    payload = {
        "version": SCHEMA_VERSION,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(records),
        "feeds": archive.get("feeds", {}),
        "meditations": records,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")


def _better(new_value, old_value):
    """True when `new_value` is worth writing over `old_value`."""
    if new_value in (None, "", [], {}):
        return False
    if old_value in (None, "", [], {}):
        return True
    return new_value != old_value


def dedupe(records: list) -> list:
    """Collapse the same recording arriving from more than one feed.

    Dharma Seed's master feed republishes every centre's talks, so the same
    episode arrives twice with two different source labels. The centre's own
    feed wins: 'Gaia House' is more useful attribution than 'Dharma Seed'.
    """
    best = {}
    for record in records:
        existing = best.get(record["id"])
        if existing is None:
            best[record["id"]] = record
            continue
        # Prefer a specific centre over the aggregator, then a real episode
        # page over none, then the richer description.
        candidates = (
            (not record["from_aggregator"], bool(record["source_url"]),
             len(record["description"] or "")),
            (not existing["from_aggregator"], bool(existing["source_url"]),
             len(existing["description"] or "")),
        )
        if candidates[0] > candidates[1]:
            best[record["id"]] = record
    return list(best.values())


def merge(archive: dict, records: list, today: str = None) -> dict:
    """Fold this run's records into the archive. Nothing is ever removed."""
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats = {"new": 0, "updated": 0, "unchanged": 0}
    store = archive["meditations"]

    for record in dedupe(records):
        existing = store.get(record["id"])
        if existing is None:
            record = dict(record)
            record["first_seen"] = today
            store[record["id"]] = record
            stats["new"] += 1
            continue

        changed = False
        for field in _UPGRADEABLE:
            if _better(record.get(field), existing.get(field)):
                existing[field] = record[field]
                changed = True
        # A record found again in a non-aggregator feed earns better attribution.
        if existing.get("from_aggregator") and not record["from_aggregator"]:
            existing["feed_name"] = record["feed_name"]
            existing["feed_slug"] = record["feed_slug"]
            existing["feed_website"] = record["feed_website"]
            existing["from_aggregator"] = False
            changed = True
        existing.setdefault("first_seen", today)
        stats["updated" if changed else "unchanged"] += 1

    archive["stats"] = stats
    return archive


def merge_feed_meta(archive: dict, results: list) -> dict:
    """Keep the last good artwork and blurb for every podcast.

    Channel metadata is archived for the same reason episodes are: a feed that
    times out once should not leave its card on the podcasts page with a blank
    square where its artwork was.
    """
    feeds = archive.setdefault("feeds", {})
    for result in results:
        if not result.ok:
            continue
        stored = feeds.setdefault(result.slug, {})
        stored["name"] = result.name
        stored["website"] = result.website
        for field in ("image", "description", "licence"):
            value = getattr(result, field, "")
            if value:
                stored[field] = value
    return archive


def prune_removed_feeds(archive: dict, configured_slugs) -> dict:
    """Drop records whose feed is no longer configured.

    The archive is otherwise append-only, which is the whole point of it. This
    is the one deliberate exception: removing a podcast from feeds.json — because
    its licence does not permit reuse, say — has to actually remove its
    recordings, its pages and its entries in the search index and RSS feed.
    """
    configured = set(configured_slugs)
    removed = {rid: rec for rid, rec in archive["meditations"].items()
               if rec.get("feed_slug") not in configured}
    for rid in removed:
        del archive["meditations"][rid]
    for slug in [s for s in archive.get("feeds", {}) if s not in configured]:
        del archive["feeds"][slug]

    by_feed = {}
    for rec in removed.values():
        by_feed[rec.get("feed_name", "?")] = by_feed.get(rec.get("feed_name", "?"), 0) + 1
    archive["pruned"] = {"count": len(removed), "by_feed": by_feed}
    return archive


def guard_build(results: list, archive_before: int, archive_after: int) -> None:
    """Refuse to publish a build that is materially worse than the last one.

    A failed run that changes nothing is strictly better than a successful run
    that quietly removes half the sources from the site.
    """
    # Licence refusals are deliberate removals, not outages; counting them here
    # would abort the build precisely when it most needs to publish the removal.
    checked = [r for r in results if not getattr(r, "licence_refused", False)]
    failed = [r for r in checked if not r.ok]
    if checked and len(failed) / len(checked) > MAX_FAILED_FEED_FRACTION:
        names = ", ".join(f"{r.name} ({r.error})" for r in failed)
        raise BuildAbandoned(
            f"{len(failed)} of {len(checked)} reachable feeds failed, above the "
            f"{MAX_FAILED_FEED_FRACTION:.0%} threshold — not publishing. {names}")

    if archive_after < archive_before:
        raise BuildAbandoned(
            f"archive would shrink from {archive_before} to {archive_after} "
            "records — refusing to write.")

    if archive_after == 0:
        raise BuildAbandoned("archive is empty — refusing to write.")


def records_for_site(archive: dict) -> list:
    """Archive records sorted newest first, with undated items last.

    Undated recordings sort to the bottom rather than being stamped with
    today's date and presented as the newest thing on the site.
    """
    records = list(archive["meditations"].values())
    records.sort(key=lambda r: (r.get("date") is not None, r.get("date") or "",
                                r.get("id", "")), reverse=True)
    return records
