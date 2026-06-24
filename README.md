# 🧘 Guided Meditations

A static website that curates **guided meditations** from a set of dharma and
insight-meditation podcasts. RSS feeds are parsed weekly, filtered down to
guided-meditation episodes, and rendered into a single fast, searchable page.

**Live site:** https://alastairrushworth.github.io/meditation/

Episodes link back to the original podcast pages so the teachers and centres
get the traffic and attribution.

## How it works

- [`generate.py`](generate.py) fetches each feed in [`feeds.json`](feeds.json),
  keeps episodes that look like guided meditations (keyword matching in
  `MEDITATION_KEYWORDS` / `EXCLUDE_KEYWORDS`), and writes:
  - `index.html` — the full page (HTML + CSS + JS inlined, no build step)
  - `sitemap.xml` — for search engines
- The page supports client-side **search**, **filter by source**, and
  **pagination** — all with no backend.
- A [GitHub Action](.github/workflows/update-meditations.yml) re-runs the
  generator every Sunday and commits any changes.

## Local development

```bash
pip install -r requirements.txt
python3 generate.py          # rebuilds index.html + sitemap.xml
python3 -m http.server 8000  # then open http://localhost:8000
```

### Regenerating branding assets

The favicon, apple-touch-icon and Open Graph share image are produced by
[`make_assets.py`](make_assets.py) (requires Pillow). They only need to be
rebuilt if the branding changes:

```bash
python3 make_assets.py
```

## Adding a feed

Add an entry to `feeds.json`:

```json
{ "name": "Display Name", "url": "https://…/rss", "website": "https://…/" }
```

## Design

Calm "sage & stone" palette, [Fraunces](https://fonts.google.com/specimen/Fraunces)
serif headings, accessible markup (real links, labelled controls, `aria-live`
result counts, visible focus styles).

## License

Code is provided as-is. Meditation content belongs to the respective teachers
and podcasts; this site only links to it.
