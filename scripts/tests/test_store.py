"""The archive is the site's memory: these tests exist because the previous
generator lost everything it did not re-fetch."""

import json

import pytest

from store import (BuildAbandoned, dedupe, guard_build, load_archive, merge,
                   merge_feed_meta, prune_removed_feeds, records_for_site,
                   save_archive)


class FakeResult:
    licence_refused = False

    def __init__(self, slug, ok=True, error="", image="", description="", name=None):
        self.slug = slug
        self.name = name or slug
        self.ok = ok
        self.error = error
        self.image = image
        self.description = description
        self.website = "https://example.com/"


def record(**overrides):
    base = {
        "id": "abc123", "slug": "a-meditation-abc123", "title": "A meditation",
        "teacher": "", "teacher_slug": "", "description": "", "date": "2026-01-01",
        "source_url": "https://example.com/ep/1", "audio_url": "https://cdn/1.mp3",
        "audio_type": "audio/mpeg", "audio_bytes": None, "duration": 1200,
        "length_bucket": "20-minutes", "practices": [], "feed_name": "Gaia House",
        "feed_slug": "gaia-house", "feed_website": "https://gaiahouse.co.uk/",
        "from_aggregator": False, "title_raw": "A meditation",
        "licence": {"id": "cc-by-nc-nd-4.0", "name": "CC BY-NC-ND 4.0",
                    "full_name": "CC", "url": "https://example.org/l"},
    }
    base.update(overrides)
    return base


def test_merge_adds_new_records():
    archive = {"version": 1, "updated": None, "meditations": {}, "feeds": {}}
    merge(archive, [record()], today="2026-01-02")
    assert len(archive["meditations"]) == 1
    assert archive["meditations"]["abc123"]["first_seen"] == "2026-01-02"


def test_merge_never_removes_what_the_feed_no_longer_lists():
    archive = {"version": 1, "updated": None, "meditations": {}, "feeds": {}}
    merge(archive, [record(id="old"), record(id="new")])
    merge(archive, [record(id="new")])          # feed has rolled the old one off
    assert set(archive["meditations"]) == {"old", "new"}


def test_merge_upgrades_empty_fields_but_never_blanks_a_good_one():
    archive = {"version": 1, "updated": None, "meditations": {}, "feeds": {}}
    merge(archive, [record(description="")])
    merge(archive, [record(description="A real description of the practice.")])
    assert archive["meditations"]["abc123"]["description"].startswith("A real")
    merge(archive, [record(description="")])
    assert archive["meditations"]["abc123"]["description"].startswith("A real")


def test_dedupe_prefers_the_centre_over_the_aggregator():
    # Dharma Seed republishes every centre's talks under its own name.
    aggregated = record(feed_name="Dharma Seed", feed_slug="dharma-seed",
                        from_aggregator=True)
    specific = record(feed_name="Spirit Rock", feed_slug="spirit-rock",
                      from_aggregator=False)
    assert dedupe([aggregated, specific])[0]["feed_name"] == "Spirit Rock"
    assert dedupe([specific, aggregated])[0]["feed_name"] == "Spirit Rock"
    assert len(dedupe([aggregated, specific])) == 1


def test_merge_reattributes_when_the_centre_feed_catches_up():
    archive = {"version": 1, "updated": None, "meditations": {}, "feeds": {}}
    merge(archive, [record(feed_name="Dharma Seed", feed_slug="dharma-seed",
                           from_aggregator=True)])
    merge(archive, [record(feed_name="Gaia House", feed_slug="gaia-house",
                           from_aggregator=False)])
    assert archive["meditations"]["abc123"]["feed_name"] == "Gaia House"


def test_guard_rejects_a_run_where_too_many_feeds_failed():
    results = [FakeResult(f"f{i}", ok=i < 5) for i in range(10)]
    with pytest.raises(BuildAbandoned, match="feeds failed"):
        guard_build(results, 100, 100)


def test_guard_tolerates_a_single_failure():
    results = [FakeResult(f"f{i}", ok=i != 0) for i in range(10)]
    guard_build(results, 100, 101)


def test_guard_refuses_to_shrink_the_archive():
    with pytest.raises(BuildAbandoned, match="shrink"):
        guard_build([FakeResult("a")], 100, 99)


def test_guard_refuses_an_empty_archive():
    with pytest.raises(BuildAbandoned, match="empty"):
        guard_build([FakeResult("a")], 0, 0)


def test_feed_metadata_survives_a_failed_fetch():
    archive = {"version": 1, "updated": None, "meditations": {}, "feeds": {}}
    merge_feed_meta(archive, [FakeResult("gaia-house", image="art.jpg",
                                         description="A retreat centre in Devon.")])
    merge_feed_meta(archive, [FakeResult("gaia-house", ok=False, error="timeout")])
    assert archive["feeds"]["gaia-house"]["image"] == "art.jpg"


def test_undated_records_sort_last_rather_than_first():
    archive = {"version": 1, "updated": None, "meditations": {}, "feeds": {}}
    merge(archive, [record(id="dated", date="2020-01-01"),
                    record(id="undated", date=None)])
    assert [r["id"] for r in records_for_site(archive)] == ["dated", "undated"]


def test_archive_round_trips(tmp_path):
    path = tmp_path / "meditations.json"
    archive = {"version": 1, "updated": None, "meditations": {}, "feeds": {}}
    merge(archive, [record()])
    merge_feed_meta(archive, [FakeResult("gaia-house", image="art.jpg")])
    save_archive(archive, path)
    reloaded = load_archive(path)
    assert reloaded["meditations"]["abc123"]["title"] == "A meditation"
    assert reloaded["feeds"]["gaia-house"]["image"] == "art.jpg"
    assert json.loads(path.read_text())["count"] == 1


def test_load_archive_handles_a_missing_file(tmp_path):
    archive = load_archive(tmp_path / "nope.json")
    assert archive["meditations"] == {}


def test_prune_removes_records_from_unconfigured_feeds():
    # The archive is append-only by design; removing a podcast from feeds.json
    # is the one deliberate exception, and it has to actually take effect.
    archive = {"version": 1, "updated": None, "meditations": {},
               "feeds": {"gaia-house": {}, "gone": {}}}
    merge(archive, [record(id="keep", feed_slug="gaia-house"),
                    record(id="drop", feed_slug="gone")])
    prune_removed_feeds(archive, {"gaia-house"})
    assert set(archive["meditations"]) == {"keep"}
    assert set(archive["feeds"]) == {"gaia-house"}
    assert archive["pruned"]["count"] == 1


def test_prune_reports_what_it_removed():
    archive = {"version": 1, "updated": None, "meditations": {}, "feeds": {}}
    merge(archive, [record(id="a", feed_slug="gone", feed_name="Gone Podcast"),
                    record(id="b", feed_slug="gone", feed_name="Gone Podcast")])
    prune_removed_feeds(archive, set())
    assert archive["pruned"]["by_feed"] == {"Gone Podcast": 2}


def test_prune_is_a_no_op_when_nothing_was_removed():
    archive = {"version": 1, "updated": None, "meditations": {}, "feeds": {}}
    merge(archive, [record(feed_slug="gaia-house")])
    prune_removed_feeds(archive, {"gaia-house"})
    assert archive["pruned"]["count"] == 0
    assert len(archive["meditations"]) == 1


def test_a_licence_refusal_is_not_counted_as_a_feed_failure():
    # Otherwise a publisher withdrawing their licence would abort the build and
    # leave their recordings published.
    results = [FakeResult(f"f{i}") for i in range(9)]
    refused = FakeResult("closed", ok=False, error="no open licence declared")
    refused.licence_refused = True
    guard_build(results + [refused], 100, 100)


def test_ordinary_failures_are_still_counted():
    results = [FakeResult(f"f{i}", ok=i < 5) for i in range(10)]
    with pytest.raises(BuildAbandoned, match="failed"):
        guard_build(results, 100, 100)
