# 🧘 Guided Meditations

A static site that indexes **guided meditations** — the practices, not the talks —
from insight-meditation and dharma podcasts. Feeds are read weekly, filtered down
to guided sittings, and rendered into a browsable, searchable archive.

**Live site:** https://alastairrushworth.com/meditation/

Nothing is hosted or re-published here. Audio streams from the original
publisher, and every recording links back to the teacher's own page, so the
centres keep their traffic and their attribution.

**Every recording is used under a Creative Commons licence.** The licence is read
from each feed on every build and enforced in code — see [Licensing](#licensing).

## How it works

`scripts/generate.py` fetches each feed in `scripts/feeds.json`, keeps the
episodes that are guided practices, merges them into the archive, and renders
the site.

**The archive is the source of truth.** `data/meditations.json` accumulates:
feeds only ever *add* to it. That matters — before it existed, the site rebuilt
itself from whatever the feeds returned that morning and kept only the two most
recent episodes per podcast, so it never grew past a couple of dozen items and
anything a search engine had indexed was gone within a week.

### Pages generated

| Path | What it is |
| --- | --- |
| `/`, `/page/N/` | The archive — every meditation, newest first, paginated, with search and filters above it |
| `/about/` | What this is, the licensing, and the list of source centres |
| `/listen/<slug>/` | Episodes whose centre publishes no page of its own — currently none, since every configured feed carries per-episode links |
| `/feed.xml` | RSS of the collection, with enclosures pointing at the original audio |
| `/search-index.json` | Compact index, fetched on demand so search covers the whole archive |
| `/podcasts.html` | Redirect stub to `/about/`; the URL has been indexed since June, so it keeps working |

**All browsing happens on the meditation page.** There is deliberately no
separate browse page, no page per centre, and no category pages for length,
practice or teacher. The archive is filtered in place: a search box, plus
length, practice and centre selects behind a disclosure. A practice tag on a
card links to `/?practice=<slug>` — back to the same page, pre-filtered.

This is a deliberate trade. Category pages were previously ~130 of the site's
161 URLs and carried most of its long-tail search surface; the site now has
about 30. Simplicity was chosen over reach.

### Modules

| File | Responsibility |
| --- | --- |
| `config.py` | Constants and taxonomies — length buckets, practices, page sizes, analytics |
| `licence.py` | Which licences permit reuse, and detecting them from a feed |
| `fetch.py` | Network, feed parsing, episode-URL resolution |
| `classify.py` | Is it a guided meditation? Whose is it? Which practice? How long? |
| `textutil.py` | Description cleaning, boilerplate stripping, slugs, truncation |
| `store.py` | Archive load/merge/save, deduplication, the degraded-build guard |
| `render.py` | Jinja2 environment, view models, structured data, asset hashing |
| `generate.py` | Orchestration |
| `check_site.py` | Post-build validation (see below) |

## Local development

```bash
pip install -r scripts/requirements-dev.txt

python3 scripts/generate.py              # fetch feeds, merge, rebuild
python3 scripts/generate.py --no-fetch   # rebuild pages from the archive only
python3 scripts/check_site.py            # validate the output
python3 scripts/serve.py                 # http://localhost:8000/meditation/
```

Use `--no-fetch` while working on templates or CSS: it rebuilds every page from
the committed archive in about three seconds and never touches the network.

`serve.py` mounts the site at `/meditation/`, the path it is served from in
production. A plain `python3 -m http.server` at the repo root will 404 every
stylesheet and link, because pages reference root-relative `/meditation/…` URLs.

### Tests

```bash
cd scripts && python3 -m pytest
```

The classifier, the text cleaners and the archive are covered. The classifier is
worth pinning down in particular: feeds change their titling conventions without
warning, and it decides what reaches the site at all.

### Post-build checks

`check_site.py` catches the failures that are invisible in a diff — unbalanced
markup, internal links to pages that were never written, sitemap entries with no
file behind them, structured data that will not parse, pages missing a title or
canonical. CI runs it on every pull request.

## Safety rails

The weekly job publishes nothing rather than publishing something worse:

- `generate.py` exits non-zero if more than a quarter of the feeds failed, if the
  archive would shrink, or if it would end up empty.
- Records are merged field by field, and a value already held is never replaced
  by an empty one — a feed that temporarily drops its descriptions cannot hollow
  out the archive.
- Channel artwork and blurbs are archived too, so a feed that times out once does
  not leave a blank square on the podcasts page.
- Fetches retry with backoff before a feed is called failed.
- Removals are always reported by name and count in the build log, so content
  never leaves the site silently.

## Licensing

This site streams recordings from their publishers' servers and reproduces
episode descriptions. Both need permission, so only podcasts that grant it are
used.

`licence.py` reads the `<copyright>` and licence fields of every feed **on every
build** and accepts only licences that permit non-commercial redistribution of
the unmodified work with attribution — the Creative Commons BY, BY-SA, BY-NC and
BY-NC-ND families. Anything else, including an absent or unrecognised statement,
means the feed contributes nothing:

- A podcast whose feed stops declaring an open licence is **not** treated as a
  failed fetch. Its recordings are pruned from the archive and disappear from
  the site, its pages, the RSS feed and the search index on the next run.
- That prune is deliberately excluded from the "too many feeds failed" guard,
  because a withdrawn licence must be able to publish its own removal rather
  than aborting the build and leaving the content up.

In return for the BY term, every card shows its teacher, its publishing centre
and a link to the exact licence; the licence notice is excluded from the
boilerplate stripper so it is never removed from a description; the RSS feed
carries per-item copyright; and `PodcastEpisode` structured data carries a
`license` field. The site carries no advertising and sells nothing, which is
what the NC term requires.

Podcasts that reserve their rights — including several well-known meditation
podcasts — are not listed here, and should not be added.

## Adding a feed

Add an entry to `scripts/feeds.json`:

```json
{
  "name": "Display Name",
  "slug": "url-safe-slug",
  "url": "https://…/rss",
  "website": "https://…/",
  "teacher": "Optional — for single-teacher podcasts",
  "aggregator": false
}
```

The licence gate runs regardless of what you add: if the feed does not declare an
open licence, the build logs a refusal and skips it. Check the build output after
adding one.

Set `aggregator: true` for a feed that republishes other centres' recordings
(Dharma Seed does). When the same episode arrives from both, deduplication keeps
the centre's own attribution rather than the aggregator's.

## Automation

- `.github/workflows/update-meditations.yml` — Sundays at 03:00 UTC: runs the
  tests, rebuilds, and commits only if something changed.
- `.github/workflows/ci.yml` — on every push and pull request: tests, a rebuild
  from the archive, and `check_site.py`.

## Analytics

Cookieless, via Plausible, so there is no consent banner and nothing personal is
stored. Configured in `config.py`; set `ANALYTICS["provider"]` to `None` to ship
no analytics at all.

## robots.txt

Crawlers only read `robots.txt` from the host root, so the copy in this repo —
served at `/meditation/robots.txt` — is ignored. The rules that apply live in the
user-site repo at `alastairrushworth.com/robots.txt`, alongside the sitemap index
that lists this section's `sitemap.xml`.

## Regenerating branding assets

The favicon, apple-touch-icon and Open Graph image come from
`scripts/make_assets.py` (requires Pillow). They only need rebuilding if the
branding changes.

## Design

Calm "sage & stone" palette in light and dark,
[Fraunces](https://fonts.google.com/specimen/Fraunces) for headings, and
progressive enhancement throughout: pagination is real links, cards are real
anchors, and every page is complete before JavaScript runs.

## License

Code is provided as-is. Meditation recordings belong to the respective teachers
and podcasts; this site indexes and links to them.
