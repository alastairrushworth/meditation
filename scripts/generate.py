#!/usr/bin/env python3
"""
Generate a static webpage listing guided meditations from podcast RSS feeds.
"""

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Tuple
import feedparser
import requests
from pathlib import Path
from html import escape as html_escape, unescape as html_unescape

SITE_URL = "https://alastairrushworth.com/meditation/"

# Show only the most recent meditations from each channel, so the homepage stays
# a fresh, skimmable snapshot rather than a long back-catalogue.
MAX_PER_FEED = 2

# Signals that an episode is a guided meditation. These are matched against the
# episode TITLE only: many dharma talks and interviews mention "guided
# meditation" in their show-notes/description, so matching the description leads
# to lots of false positives (talks, Q&As, numbered podcast episodes). Matching
# the title is both more precise (drops talks) and more thorough (catches titles
# like "Meditation: Body Scan" that don't use the exact phrase "guided
# meditation").
MEDITATION_KEYWORDS = [
    'meditation',   # "Meditation: ...", "Guided Meditation", "Metta Meditation"
    'body scan',
    'guided ',      # "Guided Reflection", "Guided Metta", "Guided Relaxation"
]

# Exclude talks / non-meditation formats even if the title matches above.
EXCLUDE_KEYWORDS = [
    'dharmette',
    'practice notes',
    'dharma talk',
    'questions and answers',
    'q&a',
    'discussion',
]

def is_guided_meditation(title: str, description: str = '') -> bool:
    """
    Determine if an episode is a guided meditation, based on its title.
    """
    title_lower = title.lower()

    # First check if it should be excluded
    for exclude in EXCLUDE_KEYWORDS:
        if exclude in title_lower:
            return False

    # Check for meditation keywords in the title
    for keyword in MEDITATION_KEYWORDS:
        if keyword in title_lower:
            return True

    return False

def parse_feed(feed_url: str, feed_name: str, feed_website: str) -> Tuple[List[Dict], Dict]:
    """
    Parse an RSS feed and extract guided meditation episodes.
    """
    print(f"Parsing feed: {feed_name}")

    # Fetch the feed with proper headers
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(feed_url, headers=headers, timeout=60)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception as e:
        print(f"  Error fetching {feed_name}: {e}")
        return [], {'name': feed_name, 'website': feed_website, 'image': '', 'description': ''}

    feed_meta = extract_feed_meta(feed, feed_name, feed_website, feed_url)
    meditations = []

    # Limit to first 50 entries to reduce processing time and keep recent content
    entries_to_process = feed.entries[:50]

    for entry in entries_to_process:
        title = entry.get('title', '')
        description = entry.get('description', '') or entry.get('summary', '')

        if is_guided_meditation(title, description):
            # Parse date
            published = entry.get('published_parsed')
            if published:
                date = datetime(*published[:6])
            else:
                date = datetime.now()

            # Get episode page link (for proper attribution and traffic to podcast)
            # The 'link' field typically points to the episode page on the podcast's website
            # This ensures podcasts get proper traffic and attribution
            episode_url = entry.get('link', '')

            # Special handling for art19.com feeds (they don't have episode page links in RSS)
            # Point to the main podcast page instead of direct MP3
            if not episode_url and 'art19.com' in feed_url:
                # Use the podcast's main website
                episode_url = feed_website

            # Fallback: if no link field and not art19, try to find any URL
            if not episode_url:
                if hasattr(entry, 'enclosures') and entry.enclosures:
                    episode_url = entry.enclosures[0].get('href')
                elif hasattr(entry, 'links') and entry.links:
                    episode_url = entry.links[0].get('href', '')

            # Get duration if available (typically in itunes:duration tag)
            duration = None
            if hasattr(entry, 'itunes_duration'):
                duration = entry.itunes_duration
            elif 'itunes_duration' in entry:
                duration = entry['itunes_duration']

            meditations.append({
                'title': title,
                'description': description,
                'date': date,
                'episode_url': episode_url or feed_website,
                'feed_name': feed_name,
                'feed_website': feed_website,
                'duration': duration
            })

    print(f"Found {len(meditations)} guided meditations from {feed_name}")
    return meditations, feed_meta

def format_duration(duration_str: str) -> str:
    """
    Format duration string to human-readable format.
    Handles both HH:MM:SS and seconds formats.
    """
    if not duration_str:
        return None

    try:
        # If it contains colons, it's already formatted
        if ':' in str(duration_str):
            parts = str(duration_str).split(':')
            if len(parts) == 3:  # HH:MM:SS
                hours, mins, secs = int(parts[0]), int(parts[1]), int(parts[2])
                if hours > 0:
                    return f"{hours}h {mins}m"
                else:
                    return f"{mins}m"
            elif len(parts) == 2:  # MM:SS
                mins, secs = int(parts[0]), int(parts[1])
                return f"{mins}m"
        else:
            # Assume it's in seconds
            total_seconds = int(duration_str)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60

            if hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
    except (ValueError, AttributeError):
        return None

def iso_duration(duration_str: str) -> str:
    """Convert a feed duration (HH:MM:SS, MM:SS or seconds) to an ISO 8601 duration."""
    if not duration_str:
        return None
    try:
        raw = str(duration_str)
        if ':' in raw:
            parts = [int(p) for p in raw.split(':')]
            if len(parts) == 3:
                hours, minutes, seconds = parts
            elif len(parts) == 2:
                hours, minutes, seconds = 0, parts[0], parts[1]
            else:
                return None
        else:
            total = int(raw)
            hours, minutes, seconds = total // 3600, (total % 3600) // 60, total % 60
    except (ValueError, AttributeError):
        return None
    out = 'PT'
    if hours:
        out += f'{hours}H'
    if minutes:
        out += f'{minutes}M'
    if seconds:
        out += f'{seconds}S'
    return out if out != 'PT' else None

def strip_tags(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub('<[^<]+?>', '', text or '')

# Boilerplate that some feeds append to every episode description (donation
# pleas, transcript notices, licence text, music credits). It carries no
# meditation-specific value and, repeated across 100+ cards, reads as templated
# / thin content to search engines. All of it trails the useful description, so
# we truncate at the first marker we recognise.
_BOILERPLATE_MARKERS = (
    'video of this talk is available',
    'machine generated transcript',
    'machine-generated transcript',
    'download transcript',
    'for more talks',
    'if you have enjoyed this talk',
    'please consider supporting',
    'this talk is licensed',
    'introduction music is from',
)

def strip_boilerplate(text: str) -> str:
    """Drop trailing per-feed boilerplate, keeping the meditation-specific intro."""
    lowered = text.lower()
    cut = len(text)
    for marker in _BOILERPLATE_MARKERS:
        idx = lowered.find(marker)
        if idx != -1:
            cut = min(cut, idx)
    trimmed = text[:cut].strip()
    if cut < len(text):
        # The boilerplate began mid-sentence (e.g. "...mind. Our introduction
        # music is from..."). Drop a short orphaned lead-in left after the last
        # complete sentence, but never a real trailing sentence.
        last = max(trimmed.rfind('.'), trimmed.rfind('!'), trimmed.rfind('?'))
        if last != -1 and len(trimmed[last + 1:].split()) <= 3:
            trimmed = trimmed[:last + 1]
    return trimmed

def description_plain(description: str) -> str:
    """Plain-text description with HTML, asterisk separators and feed boilerplate removed."""
    text = html_unescape(strip_tags(description))
    text = re.sub(r'\*{3,}', '', text)
    text = strip_boilerplate(text)
    return ' '.join(text.split())

def truncate_words(text: str, limit: int) -> str:
    """Trim to at most `limit` words, appending an ellipsis when truncated."""
    words = text.split()
    if len(words) > limit:
        return ' '.join(words[:limit]) + '...'
    return text

DHARMASEED_LOGO = "https://media.dharmaseed.org/images/DS-rss-logo.jpg"

def extract_feed_meta(feed, feed_name: str, feed_website: str, feed_url: str = '') -> Dict:
    """Pull channel-level artwork and a short blurb for the podcasts page."""
    ff = getattr(feed, 'feed', {}) or {}

    image = ''
    img = ff.get('image')
    if isinstance(img, dict):
        image = img.get('href') or img.get('url') or ''
    if not image:
        itunes_img = ff.get('itunes_image')
        if isinstance(itunes_img, dict):
            image = itunes_img.get('href') or itunes_img.get('url') or ''
    # Dharma Seed's per-centre sub-feeds carry no artwork of their own; fall back
    # to the Dharma Seed logo since these collections are hosted there.
    if not image and 'dharmaseed.org' in (feed_url or '').lower():
        image = DHARMASEED_LOGO

    description = ff.get('subtitle') or ff.get('summary') or ff.get('description') or ''
    description = truncate_words(description_plain(description), 55)

    return {
        'name': feed_name,
        'website': feed_website,
        'image': image,
        'description': description,
    }

def limit_per_feed(meditations: List[Dict], limit: int) -> List[Dict]:
    """Keep only the `limit` most recent meditations from each channel."""
    by_feed = defaultdict(list)
    for m in meditations:
        by_feed[m['feed_name']].append(m)
    kept = []
    for items in by_feed.values():
        items.sort(key=lambda x: x['date'], reverse=True)
        kept.extend(items[:limit])
    return kept

def process_description(description: str) -> str:
    """
    Clean a description (strip HTML / boilerplate), truncate to 150 words,
    escape HTML, and convert any remaining URLs to links.
    """
    description = truncate_words(description_plain(description), 150)

    # Escape HTML entities
    description = html_escape(description)

    # Convert URLs to clickable links (after escaping, so our links won't be escaped)
    # Match http://, https://, and www. URLs
    url_pattern = r'(https?://[^\s<>"{}|\\^`\[\]]+|www\.[^\s<>"{}|\\^`\[\]]+)'

    def make_link(match):
        url = match.group(1)
        # Trailing sentence punctuation should not be part of the link
        trailing = ''
        while url and url[-1] in '.,;:!?':
            trailing = url[-1] + trailing
            url = url[:-1]
        if not url:
            return match.group(1)
        # Add https:// to www. links
        href = url if url.startswith('http') else f'https://{url}'
        # Limit displayed text length for very long URLs
        display_url = url if len(url) <= 50 else url[:47] + '...'
        return (f'<a href="{href}" target="_blank" rel="noopener noreferrer">'
                f'{display_url}</a>{trailing}')

    description = re.sub(url_pattern, make_link, description)

    return description


# --------------------------------------------------------------------------
# Page template (split into pieces so CSS/JS braces stay literal)
# --------------------------------------------------------------------------

CSS = """
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg: #faf8f4;
    --bg-soft: #f3efe8;
    --surface: #fffefb;
    --text: #1c1917;
    --text-soft: #57534e;
    --muted: #6f6a61;
    --accent: #5b7553;
    --accent-strong: #455a3e;
    --accent-tint: #eef1ea;
    --border: #e7e1d8;
    --shadow: 0 1px 2px rgba(28, 25, 23, 0.04), 0 1px 3px rgba(28, 25, 23, 0.05);
    --shadow-lift: 0 10px 24px -8px rgba(28, 25, 23, 0.16);
    --radius: 14px;
    --font-serif: 'Fraunces', Georgia, 'Times New Roman', serif;
    --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', Roboto,
        'Helvetica Neue', Arial, sans-serif;
}

/* Reserve a symmetric scrollbar gutter so the centred header/content don't
   shift sideways when the vertical scrollbar appears. */
html {
    scroll-behavior: smooth;
    scrollbar-gutter: stable both-edges;
}

body {
    font-family: var(--font-sans);
    line-height: 1.65;
    color: var(--text);
    background-color: var(--bg);
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}

.container { max-width: 820px; margin: 0 auto; padding-bottom: 64px; }

/* --- Header ----------------------------------------------------------- */
header {
    position: sticky;
    top: 0;
    z-index: 100;
    padding: 44px 24px 22px;
    text-align: center;
    background: var(--bg);
}

/* Cards dissolve into a soft fade as they scroll up under the header,
   rather than meeting a hard rule and a translucent blurred seam. */
header::after {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    top: 100%;
    height: 32px;
    background: linear-gradient(to bottom, var(--bg), rgba(250, 248, 244, 0));
    pointer-events: none;
}

.brand {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    margin-bottom: 4px;
}

.brand-mark { width: 38px; height: 38px; flex-shrink: 0; }

h1 {
    font-family: var(--font-serif);
    font-size: 2.6rem;
    font-weight: 500;
    color: var(--text);
    letter-spacing: -0.015em;
    line-height: 1.1;
}

.subtitle {
    font-size: 1rem;
    color: var(--muted);
    font-weight: 400;
    margin-bottom: 22px;
}

/* --- Primary nav ------------------------------------------------------ */
.site-nav {
    display: flex;
    justify-content: center;
    gap: 8px;
    margin-top: 16px;
}

.site-nav-link {
    font-size: 0.86rem;
    font-weight: 500;
    color: var(--muted);
    text-decoration: none;
    padding: 7px 16px;
    border-radius: 999px;
    border: 1px solid transparent;
    transition: color 0.18s ease, background 0.18s ease, border-color 0.18s ease;
}

.site-nav-link:hover { color: var(--accent-strong); background: var(--bg-soft); }

.site-nav-link.active {
    color: var(--accent-strong);
    border-color: var(--border);
    background: var(--surface);
    box-shadow: var(--shadow);
}

/* --- Closing intro / blurb (rendered at the end of the page) ---------- */
.intro {
    max-width: 620px;
    margin: 40px auto 0;
    padding: 30px 24px 0;
    border-top: 1px solid var(--border);
    text-align: center;
    color: var(--text-soft);
    font-size: 0.95rem;
    line-height: 1.7;
}

/* --- Podcasts page ---------------------------------------------------- */
.podcast-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 14px;
    padding: 8px 24px 0;
}

.podcast-card {
    display: flex;
    align-items: center;
    gap: 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 16px;
    text-decoration: none;
    color: inherit;
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.podcast-card:hover {
    box-shadow: var(--shadow-lift);
    border-color: #d8cfc0;
    transform: translateY(-2px);
}

.podcast-art {
    width: 72px;
    height: 72px;
    flex-shrink: 0;
    border-radius: 10px;
    object-fit: cover;
    background: var(--accent-tint);
    border: 1px solid var(--border);
}

.podcast-info { min-width: 0; }

.podcast-name {
    font-family: var(--font-serif);
    font-size: 1.06rem;
    font-weight: 500;
    line-height: 1.3;
    margin-bottom: 4px;
    color: var(--text);
}

.podcast-card:hover .podcast-name { color: var(--accent-strong); }

.podcast-desc {
    font-size: 0.85rem;
    color: var(--text-soft);
    line-height: 1.55;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

/* --- Meditation cards ------------------------------------------------- */
main { padding: 8px 24px 0; }

.meditation {
    position: relative;
    background: var(--surface);
    margin-bottom: 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    cursor: pointer;
}

.meditation:hover {
    box-shadow: var(--shadow-lift);
    border-color: #d8cfc0;
    transform: translateY(-2px);
}

.meditation-content { padding: 22px 24px; }

.meditation-meta {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
    flex-wrap: wrap;
}

.meditation-source {
    position: relative;
    z-index: 2;
    font-size: 0.74rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--accent);
    text-decoration: none;
}

.meditation-source:hover { color: var(--accent-strong); text-decoration: underline; }

.meditation-date { font-size: 0.82rem; color: var(--muted); }

.meta-dot {
    width: 3px;
    height: 3px;
    background: #cabfae;
    border-radius: 50%;
    flex-shrink: 0;
}

.meditation-title {
    font-family: var(--font-serif);
    font-size: 1.28rem;
    font-weight: 500;
    line-height: 1.32;
    margin-bottom: 9px;
    letter-spacing: -0.01em;
}

.meditation-link { color: var(--text); text-decoration: none; }
.meditation-link:hover { color: var(--accent-strong); }

.meditation:hover .meditation-title { color: var(--accent-strong); }

.meditation-description {
    color: var(--text-soft);
    line-height: 1.65;
    font-size: 0.94rem;
    overflow-wrap: anywhere;
}

.meditation-description a {
    position: relative;
    z-index: 2;
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 2px;
    overflow-wrap: anywhere;
}

.meditation-description a:hover { color: var(--accent-strong); }

/* --- Pagination ------------------------------------------------------- */
.pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 10px;
    padding: 30px 24px 8px;
    flex-wrap: wrap;
}

.pagination-btn, .page-number {
    border: 1.5px solid var(--border);
    background: var(--surface);
    color: var(--text-soft);
    font-family: inherit;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    border-radius: 9px;
    transition: all 0.18s ease;
}

.pagination-btn { padding: 9px 16px; }
.page-number { padding: 8px 12px; min-width: 40px; text-align: center; }

.pagination-numbers { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }

.pagination-btn:hover:not(:disabled),
.page-number:hover { border-color: #cabfae; background: var(--bg-soft); }

.pagination-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.page-number.active {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
}

.page-ellipsis { padding: 8px 4px; color: var(--muted); }

/* --- Footer ----------------------------------------------------------- */
footer {
    text-align: center;
    padding: 44px 24px 8px;
    color: var(--muted);
    font-size: 0.84rem;
}

footer p { margin: 5px 0; }
footer a { color: var(--accent); text-decoration: none; }
footer a:hover { color: var(--accent-strong); text-decoration: underline; }

/* --- Utilities -------------------------------------------------------- */
.hidden { display: none !important; }

.sr-only {
    position: absolute;
    width: 1px; height: 1px;
    padding: 0; margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}

a:focus-visible,
button:focus-visible,
input:focus-visible,
.meditation:focus-within {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
}

::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #d8cfc0; border-radius: 5px; }
::-webkit-scrollbar-thumb:hover { background: #c2b6a3; }

@media (prefers-reduced-motion: reduce) {
    html { scroll-behavior: auto; }
    * { transition: none !important; }
    .meditation:hover { transform: none; }
}

@media (max-width: 768px) {
    h1 { font-size: 2.1rem; }
    header { padding: 30px 18px 22px; }
    .subtitle { font-size: 0.92rem; }
    .intro { font-size: 0.9rem; }
    main { padding: 8px 16px 0; }
    .meditation-content { padding: 18px 18px; }
    .meditation-title { font-size: 1.14rem; }
    .meditation-description { font-size: 0.9rem; }
    .pagination { padding: 24px 16px 4px; gap: 8px; }
    .podcast-grid { padding: 8px 16px 0; }
    .intro { font-size: 0.9rem; padding-top: 26px; }
}
"""


JS = """
const meditationEls = Array.from(document.querySelectorAll('.meditation'));
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const paginationNumbers = document.getElementById('pagination-numbers');
const resultsEl = document.getElementById('results');

let currentPage = 1;
const totalItems = meditationEls.length;

function render(scroll) {
    const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const endIndex = startIndex + ITEMS_PER_PAGE;

    meditationEls.forEach((m, index) => {
        m.classList.toggle('hidden', index < startIndex || index >= endIndex);
    });

    renderPagination(totalPages);

    if (scroll && resultsEl) {
        resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function renderPagination(totalPages) {
    prevBtn.disabled = currentPage === 1;
    nextBtn.disabled = currentPage === totalPages || totalPages === 0;
    paginationNumbers.innerHTML = '';
    if (totalPages <= 1) return;

    const maxVisible = 7;
    let pages = [];
    if (totalPages <= maxVisible) {
        for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else if (currentPage <= 4) {
        pages = [1, 2, 3, 4, 5, '...', totalPages];
    } else if (currentPage >= totalPages - 3) {
        pages = [1, '...', totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
    } else {
        pages = [1, '...', currentPage - 1, currentPage, currentPage + 1, '...', totalPages];
    }

    pages.forEach(page => {
        if (page === '...') {
            const ell = document.createElement('span');
            ell.className = 'page-ellipsis';
            ell.textContent = '...';
            paginationNumbers.appendChild(ell);
        } else {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'page-number' + (page === currentPage ? ' active' : '');
            btn.textContent = page;
            if (page === currentPage) btn.setAttribute('aria-current', 'page');
            btn.addEventListener('click', () => goToPage(page));
            paginationNumbers.appendChild(btn);
        }
    });
}

function goToPage(page) {
    currentPage = page;
    render(true);
}

prevBtn.addEventListener('click', () => { if (currentPage > 1) goToPage(currentPage - 1); });
nextBtn.addEventListener('click', () => {
    const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);
    if (currentPage < totalPages) goToPage(currentPage + 1);
});

// Whole-card click for mouse users (keyboard users use the real title link).
// Ignore clicks on links and clicks made while selecting text.
meditationEls.forEach(el => {
    el.addEventListener('click', e => {
        if (e.target.closest('a')) return;
        if (window.getSelection().toString().length) return;
        const link = el.querySelector('.meditation-link');
        if (link) window.open(link.href, '_blank', 'noopener');
    });
});

render(false);
"""


LOTUS_SVG = (
    '<svg class="brand-mark" viewBox="0 0 64 64" aria-hidden="true" '
    'focusable="false"><g fill="#5b7553" fill-opacity="0.82">'
    '<path d="M32 50 C27 42 27 27 32 15 C37 27 37 42 32 50Z" transform="rotate(-75 32 50)"/>'
    '<path d="M32 50 C27 42 27 27 32 15 C37 27 37 42 32 50Z" transform="rotate(-50 32 50)"/>'
    '<path d="M32 50 C27 42 27 27 32 15 C37 27 37 42 32 50Z" transform="rotate(-25 32 50)"/>'
    '<path d="M32 50 C27 42 27 27 32 15 C37 27 37 42 32 50Z" transform="rotate(0 32 50)"/>'
    '<path d="M32 50 C27 42 27 27 32 15 C37 27 37 42 32 50Z" transform="rotate(25 32 50)"/>'
    '<path d="M32 50 C27 42 27 27 32 15 C37 27 37 42 32 50Z" transform="rotate(50 32 50)"/>'
    '<path d="M32 50 C27 42 27 27 32 15 C37 27 37 42 32 50Z" transform="rotate(75 32 50)"/>'
    '</g></svg>'
)


def build_nav(active: str) -> str:
    """Primary nav shared by the pages; `active` is 'meditations' or 'podcasts'."""
    links = [('meditations', 'index.html', 'Meditations'),
             ('podcasts', 'podcasts.html', 'Podcasts')]
    items = []
    for key, href, label in links:
        cls = 'site-nav-link active' if key == active else 'site-nav-link'
        current = ' aria-current="page"' if key == active else ''
        items.append(f'<a href="{href}" class="{cls}"{current}>{label}</a>')
    joined = '\n                '.join(items)
    return ('<nav class="site-nav" aria-label="Primary">\n'
            f'                {joined}\n'
            '            </nav>')


def build_head(title: str, description: str, canonical: str, json_ld: str = None) -> str:
    """Shared <head> for the site's pages."""
    og_image = SITE_URL + "og-image.png"

    gtag = (
        '<script async src="https://www.googletagmanager.com/gtag/js?id=G-Y8XLWX2T51"></script>\n'
        '    <script>\n'
        '      window.dataLayer = window.dataLayer || [];\n'
        '      function gtag(){dataLayer.push(arguments);}\n'
        "      gtag('js', new Date());\n"
        "      gtag('config', 'G-Y8XLWX2T51');\n"
        '    </script>'
    )

    ld_block = ''
    if json_ld:
        ld_block = (
            '    <!-- Structured Data / JSON-LD -->\n'
            '    <script type="application/ld+json">\n'
            f'{json_ld}\n'
            '    </script>\n\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <!-- Primary Meta Tags -->
    <title>{html_escape(title)}</title>
    <meta name="title" content="{html_escape(title)}">
    <meta name="description" content="{html_escape(description)}">
    <meta name="author" content="Alastair Rushworth">
    <meta name="robots" content="index, follow">
    <meta name="theme-color" content="#faf8f4">
    <link rel="canonical" href="{canonical}">

    <!-- Icons -->
    <link rel="icon" href="favicon.svg" type="image/svg+xml">
    <link rel="icon" href="favicon-32.png" sizes="32x32" type="image/png">
    <link rel="apple-touch-icon" href="apple-touch-icon.png">
    <link rel="manifest" href="site.webmanifest">

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical}">
    <meta property="og:title" content="{html_escape(title)}">
    <meta property="og:description" content="{html_escape(description)}">
    <meta property="og:site_name" content="Guided Meditations">
    <meta property="og:locale" content="en_US">
    <meta property="og:image" content="{og_image}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:image:alt" content="Guided Meditations — a curated collection from dharma podcasts">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="{canonical}">
    <meta name="twitter:title" content="{html_escape(title)}">
    <meta name="twitter:description" content="{html_escape(description)}">
    <meta name="twitter:image" content="{og_image}">

{ld_block}    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&display=swap">

    <style>{CSS}</style>
    {gtag}
</head>
"""


def build_json_ld(meditations: List[Dict]) -> str:
    """Build schema.org structured data for the collection."""
    def list_item(position: int, m: Dict) -> Dict:
        item = {
            "@type": "PodcastEpisode",
            "name": html_unescape(strip_tags(m['title'])).strip(),
            "url": m['episode_url'] or m['feed_website'],
            "datePublished": m['date'].strftime('%Y-%m-%d'),
            "partOfSeries": {"@type": "PodcastSeries", "name": m['feed_name']},
        }
        duration = iso_duration(m.get('duration'))
        if duration:
            item["duration"] = duration
        return {"@type": "ListItem", "position": position, "item": item}

    item_list = {
        "@type": "ItemList",
        "itemListOrder": "https://schema.org/ItemListOrderDescending",
        "numberOfItems": len(meditations),
        "itemListElement": [list_item(i + 1, m) for i, m in enumerate(meditations)],
    }
    website = {
        "@type": "WebSite",
        "@id": SITE_URL + "#website",
        "name": "Guided Meditations",
        "url": SITE_URL,
        "description": "A curated collection of guided meditations from dharma podcasts.",
        "inLanguage": "en",
        "author": {"@type": "Person", "name": "Alastair Rushworth", "url": "https://alastairrushworth.com"},
        "publisher": {"@type": "Person", "name": "Alastair Rushworth"},
    }
    collection = {
        "@type": "CollectionPage",
        "@id": SITE_URL + "#webpage",
        "url": SITE_URL,
        "name": "Guided Meditations – Curated Collection from Dharma Podcasts",
        "isPartOf": {"@id": SITE_URL + "#website"},
        "inLanguage": "en",
        "about": "guided meditation, mindfulness, dharma",
        "mainEntity": item_list,
    }
    graph = {"@context": "https://schema.org", "@graph": [website, collection]}
    return json.dumps(graph, ensure_ascii=False, indent=2)


def generate_html(meditations: List[Dict], output_file: str):
    """
    Generate a static HTML page with the guided meditations.
    """
    # Sort by date, most recent first
    meditations.sort(key=lambda x: x['date'], reverse=True)
    total_count = len(meditations)

    json_ld = build_json_ld(meditations)
    meta_description = (
        f"Browse {total_count} free guided meditations from teachers like Tara Brach, "
        "Jack Kornfield & Sharon Salzberg — mindfulness, body scan and metta practice."
    )
    title = "Guided Meditations – Curated Collection from Dharma Podcasts"

    head = build_head(title, meta_description, SITE_URL, json_ld)

    nav_html = build_nav('meditations')

    body_open = f"""<body>
    <div class="container">
        <header>
            <div class="brand">
                {LOTUS_SVG}
                <h1>Guided Meditations</h1>
            </div>
            <p class="subtitle">A curated collection from dharma podcasts</p>
            {nav_html}
        </header>

        <main id="results">
"""

    cards = []
    for m in meditations:
        date_str = m['date'].strftime('%B %d, %Y')
        date_iso = m['date'].strftime('%Y-%m-%d')
        duration_str = format_duration(m.get('duration'))

        title_plain = html_unescape(strip_tags(m['title'])).strip()
        title_attr = html_escape(title_plain)

        description_html = process_description(m['description'])

        feed_website = html_escape(m['feed_website'])
        episode_url = html_escape(m['episode_url'])
        feed_name = html_escape(m['feed_name'])

        meta_html = f'<time class="meditation-date" datetime="{date_iso}">{date_str}</time>'
        if duration_str:
            meta_html += (
                '\n                        <span class="meta-dot" aria-hidden="true"></span>'
                f'\n                        <span class="meditation-date">{duration_str}</span>'
            )

        cards.append(f"""
            <article class="meditation">
                <div class="meditation-content">
                    <div class="meditation-meta">
                        <a href="{feed_website}" class="meditation-source" target="_blank" rel="noopener noreferrer">{feed_name}</a>
                        <span class="meta-dot" aria-hidden="true"></span>
                        {meta_html}
                    </div>
                    <h2 class="meditation-title"><a class="meditation-link" href="{episode_url}" target="_blank" rel="noopener noreferrer">{title_attr}</a></h2>
                    <div class="meditation-description">{description_html}</div>
                </div>
            </article>
""")

    body_close = """
        </main>

        <nav class="pagination" id="pagination" aria-label="Pagination">
            <button type="button" class="pagination-btn" id="prev-btn" disabled>&laquo; Previous</button>
            <div class="pagination-numbers" id="pagination-numbers"></div>
            <button type="button" class="pagination-btn" id="next-btn">Next &raquo;</button>
        </nav>

        <p class="intro">A hand-picked, regularly updated collection of free guided
        meditations from leading insight-meditation and dharma podcasts &mdash; practices
        for mindfulness, the body scan, loving-kindness (metta) and compassion from teachers
        including Tara Brach, Jack Kornfield, Sharon Salzberg, Joseph Goldstein and Ajahn
        Brahm. Every meditation links back to its original source.</p>

        <footer>
            <p>Last updated: {update_time}</p>
            <p>Generated from podcast RSS feeds &middot; not affiliated with the teachers or centres listed</p>
            <p>
                <a href="podcasts.html">Browse podcasts</a> &middot;
                <a href="https://github.com/alastairrushworth/meditation" target="_blank" rel="noopener noreferrer">View on GitHub</a> &middot;
                Made by <a href="https://alastairrushworth.com" target="_blank" rel="noopener noreferrer">alastairrushworth.com</a>
            </p>
        </footer>
    </div>

    <script>
const ITEMS_PER_PAGE = 25;
{JS}
    </script>
</body>
</html>
""".format(update_time=datetime.now().strftime('%B %d, %Y'), JS=JS)

    html = head + body_open + ''.join(cards) + body_close

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Generated {output_file} with {total_count} meditations")


def build_podcasts_json_ld(feed_metas: List[Dict]) -> str:
    """schema.org ItemList of the source podcasts."""
    def list_item(position: int, fm: Dict) -> Dict:
        series = {"@type": "PodcastSeries", "name": fm['name'], "url": fm['website']}
        if fm.get('image'):
            series["image"] = fm['image']
        if fm.get('description'):
            series["description"] = fm['description']
        return {"@type": "ListItem", "position": position, "item": series}

    page = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "url": SITE_URL + "podcasts.html",
        "name": "Podcasts – Guided Meditation Sources",
        "isPartOf": {"@id": SITE_URL + "#website"},
        "inLanguage": "en",
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(feed_metas),
            "itemListElement": [list_item(i + 1, fm) for i, fm in enumerate(feed_metas)],
        },
    }
    return json.dumps(page, ensure_ascii=False, indent=2)


def generate_podcasts_html(feed_metas: List[Dict], output_file: str):
    """Generate a page listing the source podcasts with artwork and links."""
    canonical = SITE_URL + "podcasts.html"
    title = "Podcasts – Guided Meditation Sources"
    meta_description = (
        "The dharma and insight-meditation podcasts behind this collection of guided "
        "meditations — Tara Brach, Jack Kornfield, Sharon Salzberg, Joseph Goldstein, "
        "Ajahn Brahm and more."
    )
    json_ld = build_podcasts_json_ld(feed_metas)
    head = build_head(title, meta_description, canonical, json_ld)

    nav_html = build_nav('podcasts')

    cards = []
    for fm in feed_metas:
        name = html_escape(fm['name'])
        website = html_escape(fm['website'])
        if fm.get('image'):
            art = (
                f'<img class="podcast-art" src="{html_escape(fm["image"])}" '
                f'alt="{name} artwork" loading="lazy" width="72" height="72">'
            )
        else:
            art = '<div class="podcast-art" aria-hidden="true"></div>'
        desc_html = ''
        if fm.get('description'):
            desc_html = f'<p class="podcast-desc">{html_escape(fm["description"])}</p>'
        cards.append(f"""
            <a class="podcast-card" href="{website}" target="_blank" rel="noopener noreferrer">
                {art}
                <div class="podcast-info">
                    <div class="podcast-name">{name}</div>
                    {desc_html}
                </div>
            </a>
""")

    body = f"""<body>
    <div class="container">
        <header>
            <div class="brand">
                {LOTUS_SVG}
                <h1>Guided Meditations</h1>
            </div>
            <p class="subtitle">The podcasts behind the collection</p>
            {nav_html}
        </header>

        <main class="podcast-grid">
{''.join(cards)}        </main>

        <p class="intro">Every meditation on this site links back to its original
        source. These are the insight-meditation and dharma podcasts the collection draws
        from &mdash; visit them to support the teachers and explore their full archives.</p>

        <footer>
            <p>Generated from podcast RSS feeds &middot; not affiliated with the teachers or centres listed</p>
            <p>
                <a href="index.html">Browse meditations</a> &middot;
                <a href="https://github.com/alastairrushworth/meditation" target="_blank" rel="noopener noreferrer">View on GitHub</a> &middot;
                Made by <a href="https://alastairrushworth.com" target="_blank" rel="noopener noreferrer">alastairrushworth.com</a>
            </p>
        </footer>
    </div>
</body>
</html>
"""

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(head + body)
    print(f"Generated {output_file} with {len(feed_metas)} podcasts")


def generate_sitemap(output_file: str):
    """Write a minimal sitemap for the single-page site."""
    lastmod = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{SITE_URL}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{SITE_URL}podcasts.html</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
</urlset>
"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(sitemap)
    print(f"Generated {output_file}")


def main():
    """
    Main function to process all feeds and generate the webpage.
    """
    # Load feeds configuration
    feeds_file = Path(__file__).parent / 'feeds.json'
    with open(feeds_file, 'r') as f:
        config = json.load(f)

    all_meditations = []
    feed_metas = []

    # Process each feed
    for feed in config['feeds']:
        meditations, feed_meta = parse_feed(feed['url'], feed['name'], feed['website'])
        all_meditations.extend(meditations)
        feed_metas.append(feed_meta)

    # Keep only the two most recent meditations from each channel.
    all_meditations = limit_per_feed(all_meditations, MAX_PER_FEED)

    # Generate outputs at the repo root (this script lives in scripts/).
    site_root = Path(__file__).parent.parent
    generate_html(all_meditations, str(site_root / 'index.html'))
    generate_podcasts_html(feed_metas, str(site_root / 'podcasts.html'))
    generate_sitemap(str(site_root / 'sitemap.xml'))

    print(f"\nSuccess! Open {site_root / 'index.html'} in your browser to view the meditations.")

if __name__ == '__main__':
    main()
