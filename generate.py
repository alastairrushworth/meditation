#!/usr/bin/env python3
"""
Generate a static webpage listing guided meditations from podcast RSS feeds.
"""

import json
import re
from datetime import datetime
from typing import List, Dict
import feedparser
import requests
from pathlib import Path
from html import escape as html_escape

# Keywords to identify guided meditations
MEDITATION_KEYWORDS = [
    'guided meditation',
    'guided meditaton',  # common typo in feed
    'body scan',
    'breath meditation',
    'mindfulness meditation',
    'sitting meditation',
    'walking meditation',
    'compassion meditation',
    'awareness meditation'
]

# Exclude talks that are not meditations
EXCLUDE_KEYWORDS = [
    'dharmette',
    'practice notes',
    'dharma talk',
    'questions and answers',
    'q&a',
    'discussion'
]

def is_guided_meditation(title: str, description: str) -> bool:
    """
    Determine if an episode is a guided meditation based on title and description.
    """
    title_lower = title.lower()
    text_lower = f"{title_lower} {description.lower()}"

    # First check if it should be excluded
    for exclude in EXCLUDE_KEYWORDS:
        if exclude in title_lower:
            return False

    # Check for meditation keywords
    for keyword in MEDITATION_KEYWORDS:
        if keyword in text_lower:
            return True

    return False

def parse_feed(feed_url: str, feed_name: str, feed_website: str) -> List[Dict]:
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
        return []

    meditations = []

    for entry in feed.entries:
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

            meditations.append({
                'title': title,
                'description': description,
                'date': date,
                'episode_url': episode_url,
                'feed_name': feed_name,
                'feed_website': feed_website
            })

    print(f"Found {len(meditations)} guided meditations from {feed_name}")
    return meditations

def generate_html(meditations: List[Dict], output_file: str):
    """
    Generate a static HTML page with the guided meditations.
    """
    # Sort by date, most recent first
    meditations.sort(key=lambda x: x['date'], reverse=True)

    # Get unique podcast names for filter pills
    podcast_names = sorted(set(m['feed_name'] for m in meditations))
    podcast_pills = '\n'.join([f'<div class="filter-pill" data-podcast="{html_escape(name)}">{html_escape(name)}</div>' for name in podcast_names])

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Guided Meditations</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif;
            line-height: 1.6;
            color: #2c3e50;
            background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }}

        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding-bottom: 60px;
        }}

        header {{
            padding: 48px 24px 32px;
            text-align: center;
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            position: sticky;
            top: 0;
            z-index: 100;
            border-bottom: 1px solid rgba(0, 0, 0, 0.05);
        }}

        h1 {{
            font-size: 2.5em;
            margin-bottom: 6px;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            letter-spacing: -0.02em;
        }}

        .subtitle {{
            font-size: 1em;
            color: #64748b;
            font-weight: 400;
            margin-bottom: 24px;
        }}

        .search-box {{
            max-width: 500px;
            margin: 0 auto;
            position: relative;
        }}

        .search-input {{
            width: 100%;
            padding: 14px 20px;
            border: 2px solid transparent;
            border-radius: 12px;
            font-size: 1em;
            background: white;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            transition: all 0.3s ease;
        }}

        .search-input:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
        }}

        .search-input::placeholder {{
            color: #94a3b8;
        }}

        .filters {{
            padding: 16px 24px;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }}

        .filter-pills {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            justify-content: center;
            min-height: 32px;
        }}

        .filter-pill {{
            padding: 6px 14px;
            border-radius: 16px;
            border: 1.5px solid #e2e8f0;
            background: white;
            color: #64748b;
            font-size: 0.8em;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
            user-select: none;
        }}

        .filter-pill:hover {{
            border-color: #cbd5e1;
            background: #f8fafc;
        }}

        .filter-pill.active {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-color: transparent;
        }}

        .result-count {{
            text-align: center;
            margin: 16px 0 8px;
            color: #94a3b8;
            font-size: 0.9em;
        }}

        main {{
            padding: 0 24px;
        }}

        .meditation {{
            background: white;
            margin-bottom: 16px;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            transition: all 0.3s ease;
            cursor: pointer;
        }}

        .meditation:hover {{
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
            transform: translateY(-2px);
        }}

        .meditation-content {{
            padding: 24px;
        }}

        .meditation-meta {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
            flex-wrap: wrap;
        }}

        .meditation-source {{
            font-size: 0.8em;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #667eea;
            text-decoration: none;
        }}

        .meditation-date {{
            font-size: 0.85em;
            color: #94a3b8;
        }}

        .meta-dot {{
            width: 3px;
            height: 3px;
            background: #cbd5e1;
            border-radius: 50%;
        }}

        .meditation-title {{
            font-size: 1.25em;
            font-weight: 600;
            color: #1e293b;
            line-height: 1.4;
            margin-bottom: 10px;
        }}

        .meditation-description {{
            color: #64748b;
            line-height: 1.6;
            font-size: 0.95em;
        }}

        footer {{
            text-align: center;
            padding: 40px 24px;
            color: #94a3b8;
            font-size: 0.85em;
        }}

        footer p {{
            margin: 6px 0;
        }}

        footer a {{
            color: #667eea;
            text-decoration: none;
            transition: color 0.2s ease;
        }}

        footer a:hover {{
            color: #764ba2;
            text-decoration: underline;
        }}

        .pagination {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 12px;
            padding: 32px 24px;
            flex-wrap: wrap;
        }}

        .pagination-btn {{
            padding: 10px 18px;
            border: 2px solid #e2e8f0;
            background: white;
            color: #64748b;
            font-size: 0.9em;
            font-weight: 500;
            cursor: pointer;
            border-radius: 8px;
            transition: all 0.2s ease;
            user-select: none;
        }}

        .pagination-btn:hover:not(:disabled) {{
            border-color: #667eea;
            color: #667eea;
            background: #f8fafc;
        }}

        .pagination-btn:disabled {{
            opacity: 0.4;
            cursor: not-allowed;
        }}

        .pagination-numbers {{
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            justify-content: center;
        }}

        .page-number {{
            padding: 8px 12px;
            border: 2px solid #e2e8f0;
            background: white;
            color: #64748b;
            font-size: 0.9em;
            font-weight: 500;
            cursor: pointer;
            border-radius: 8px;
            transition: all 0.2s ease;
            user-select: none;
            min-width: 40px;
            text-align: center;
        }}

        .page-number:hover {{
            border-color: #cbd5e1;
            background: #f8fafc;
        }}

        .page-number.active {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-color: transparent;
        }}

        .page-ellipsis {{
            padding: 8px 4px;
            color: #94a3b8;
            user-select: none;
        }}

        .hidden {{
            display: none !important;
        }}

        .highlight {{
            background: linear-gradient(135deg, #fef08a 0%, #fde047 100%);
            padding: 2px 4px;
            border-radius: 3px;
        }}

        /* Scrollbar styling */
        ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}

        ::-webkit-scrollbar-track {{
            background: transparent;
        }}

        ::-webkit-scrollbar-thumb {{
            background: #cbd5e1;
            border-radius: 4px;
        }}

        ::-webkit-scrollbar-thumb:hover {{
            background: #94a3b8;
        }}

        @media (max-width: 768px) {{
            h1 {{
                font-size: 2em;
            }}

            header {{
                padding: 32px 20px 24px;
            }}

            .subtitle {{
                font-size: 0.9em;
            }}

            main {{
                padding: 0 16px;
            }}

            .filters {{
                padding: 16px;
            }}

            .filter-pills {{
                justify-content: flex-start;
            }}

            .meditation-content {{
                padding: 20px;
            }}

            .meditation-title {{
                font-size: 1.1em;
            }}

            .meditation-description {{
                font-size: 0.9em;
            }}

            .pagination {{
                padding: 24px 16px;
                gap: 8px;
            }}

            .pagination-btn {{
                padding: 8px 14px;
                font-size: 0.85em;
            }}

            .page-number {{
                padding: 6px 10px;
                font-size: 0.85em;
                min-width: 36px;
            }}
        }}
    </style>
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-Y8XLWX2T51"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());

      gtag('config', 'G-Y8XLWX2T51');
    </script>
</head>
<body>
    <div class="container">
        <header>
            <h1>Guided Meditations</h1>
            <p class="subtitle">A curated collection from dharma podcasts</p>
            <div class="search-box">
                <input type="text" id="search-input" class="search-input" placeholder="Search meditations...">
            </div>
        </header>

        <div class="filters">
            <div class="filter-pills" id="filter-pills">
                <div class="filter-pill active" data-podcast="all">All</div>
                {podcast_pills}
            </div>
            <div class="result-count" id="result-count">Showing {total_count} meditations</div>
        </div>

        <main>
"""

    for meditation in meditations:
        date_str = meditation['date'].strftime('%B %d, %Y')

        # Strip HTML tags and escape HTML entities
        title = re.sub('<[^<]+?>', '', meditation['title'])
        title = html_escape(title)

        description = meditation['description'][:300] + '...' if len(meditation['description']) > 300 else meditation['description']
        description = re.sub('<[^<]+?>', '', description)
        description = html_escape(description)

        # Escape URLs
        feed_website = html_escape(meditation['feed_website'])
        episode_url = html_escape(meditation['episode_url'])
        feed_name = html_escape(meditation['feed_name'])

        html += f"""
            <div class="meditation" data-podcast="{feed_name}" data-title="{title.lower()}" data-description="{description.lower()}" data-original-title="{title}" data-original-description="{description}" data-url="{episode_url}">
                <div class="meditation-content">
                    <div class="meditation-meta">
                        <a href="{feed_website}" class="meditation-source" target="_blank" onclick="event.stopPropagation();">{feed_name}</a>
                        <div class="meta-dot"></div>
                        <div class="meditation-date">{date_str}</div>
                    </div>
                    <div class="meditation-title">{title}</div>
                    <div class="meditation-description">{description}</div>
                </div>
            </div>
"""

    html += """
        </main>

        <div class="pagination" id="pagination">
            <button class="pagination-btn" id="prev-btn" disabled>&laquo; Previous</button>
            <div class="pagination-numbers" id="pagination-numbers"></div>
            <button class="pagination-btn" id="next-btn">Next &raquo;</button>
        </div>

        <footer>
            <p>Last updated: {update_time}</p>
            <p>Generated from podcast RSS feeds</p>
            <p>
                <a href="https://github.com/alastairrushworth/meditation" target="_blank">View on GitHub</a> |
                Made by <a href="https://alastairrushworth.com" target="_blank">alastairrushworth.com</a>
            </p>
        </footer>
    </div>

    <script>
        // Filter, search, and pagination functionality
        const filterPills = document.querySelectorAll('.filter-pill');
        const searchInput = document.getElementById('search-input');
        const resultCount = document.getElementById('result-count');
        const meditations = document.querySelectorAll('.meditation');
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');
        const paginationNumbers = document.getElementById('pagination-numbers');

        const ITEMS_PER_PAGE = 25;
        let selectedPodcast = 'all';
        let currentPage = 1;
        let filteredMeditations = [];

        function escapeRegExp(string) {{
            return string.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
        }}

        function highlightText(text, searchTerm) {{
            if (!searchTerm) return text;

            const escapedTerm = escapeRegExp(searchTerm);
            const regex = new RegExp(`(${{escapedTerm}})`, 'gi');
            return text.replace(regex, '<span class="highlight">$1</span>');
        }}

        function applyFilters() {{
            const searchTerm = searchInput.value.toLowerCase().trim();
            filteredMeditations = [];

            // First pass: determine which meditations match filters
            meditations.forEach(meditation => {{
                const podcast = meditation.getAttribute('data-podcast');
                const title = meditation.getAttribute('data-title');
                const description = meditation.getAttribute('data-description');
                const originalTitle = meditation.getAttribute('data-original-title');
                const originalDescription = meditation.getAttribute('data-original-description');

                // Check podcast filter
                const podcastMatch = selectedPodcast === 'all' || podcast === selectedPodcast;

                // Check search term
                const searchMatch = searchTerm === '' ||
                                   title.includes(searchTerm) ||
                                   description.includes(searchTerm);

                if (podcastMatch && searchMatch) {{
                    filteredMeditations.push({{
                        element: meditation,
                        originalTitle: originalTitle,
                        originalDescription: originalDescription
                    }});
                }}
            }});

            // Reset to page 1 when filters change
            currentPage = 1;

            // Apply pagination
            applyPagination(searchTerm);
        }}

        function applyPagination(searchTerm = '') {{
            const totalPages = Math.ceil(filteredMeditations.length / ITEMS_PER_PAGE);
            const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
            const endIndex = startIndex + ITEMS_PER_PAGE;

            // Hide all meditations first
            meditations.forEach(m => m.classList.add('hidden'));

            // Show only the meditations for the current page
            filteredMeditations.forEach((item, index) => {{
                const meditation = item.element;
                const titleElement = meditation.querySelector('.meditation-title');
                const descriptionElement = meditation.querySelector('.meditation-description');

                if (index >= startIndex && index < endIndex) {{
                    meditation.classList.remove('hidden');

                    // Apply highlighting if there's a search term
                    if (searchTerm) {{
                        titleElement.innerHTML = highlightText(item.originalTitle, searchTerm);
                        descriptionElement.innerHTML = highlightText(item.originalDescription, searchTerm);
                    }} else {{
                        titleElement.textContent = item.originalTitle;
                        descriptionElement.textContent = item.originalDescription;
                    }}
                }}
            }});

            // Update result count
            const totalText = selectedPodcast === 'all' ? '{total_count}' : '';
            const showing = Math.min(filteredMeditations.length, endIndex) - startIndex;

            if (filteredMeditations.length === 0) {{
                resultCount.textContent = 'No meditations found';
            }} else if (totalText && filteredMeditations.length < {total_count}) {{
                resultCount.textContent = `Showing ${{startIndex + 1}}-${{startIndex + showing}} of ${{filteredMeditations.length}} meditations`;
            }} else {{
                resultCount.textContent = `Showing ${{startIndex + 1}}-${{startIndex + showing}} of ${{filteredMeditations.length}} meditations`;
            }}

            // Update pagination controls
            renderPagination(totalPages);

            // Scroll to top
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        function renderPagination(totalPages) {{
            // Update prev/next buttons
            prevBtn.disabled = currentPage === 1;
            nextBtn.disabled = currentPage === totalPages || totalPages === 0;

            // Clear pagination numbers
            paginationNumbers.innerHTML = '';

            if (totalPages <= 1) {{
                return; // Don't show pagination for single page
            }}

            // Generate page numbers with ellipsis
            const maxVisible = 7;
            let pages = [];

            if (totalPages <= maxVisible) {{
                // Show all pages
                for (let i = 1; i <= totalPages; i++) {{
                    pages.push(i);
                }}
            }} else {{
                // Show pages with ellipsis
                if (currentPage <= 4) {{
                    pages = [1, 2, 3, 4, 5, '...', totalPages];
                }} else if (currentPage >= totalPages - 3) {{
                    pages = [1, '...', totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
                }} else {{
                    pages = [1, '...', currentPage - 1, currentPage, currentPage + 1, '...', totalPages];
                }}
            }}

            // Render page numbers
            pages.forEach(page => {{
                if (page === '...') {{
                    const ellipsis = document.createElement('span');
                    ellipsis.className = 'page-ellipsis';
                    ellipsis.textContent = '...';
                    paginationNumbers.appendChild(ellipsis);
                }} else {{
                    const pageBtn = document.createElement('div');
                    pageBtn.className = 'page-number' + (page === currentPage ? ' active' : '');
                    pageBtn.textContent = page;
                    pageBtn.addEventListener('click', () => goToPage(page));
                    paginationNumbers.appendChild(pageBtn);
                }}
            }});
        }}

        function goToPage(page) {{
            currentPage = page;
            const searchTerm = searchInput.value.toLowerCase().trim();
            applyPagination(searchTerm);
        }}

        // Filter pill click handlers
        filterPills.forEach(pill => {{
            pill.addEventListener('click', function() {{
                filterPills.forEach(p => p.classList.remove('active'));
                this.classList.add('active');
                selectedPodcast = this.getAttribute('data-podcast');
                applyFilters();
            }});
        }});

        // Search input handler
        searchInput.addEventListener('input', applyFilters);

        // Pagination button handlers
        prevBtn.addEventListener('click', () => {{
            if (currentPage > 1) {{
                goToPage(currentPage - 1);
            }}
        }});

        nextBtn.addEventListener('click', () => {{
            const totalPages = Math.ceil(filteredMeditations.length / ITEMS_PER_PAGE);
            if (currentPage < totalPages) {{
                goToPage(currentPage + 1);
            }}
        }});

        // Make meditation cards clickable
        meditations.forEach(meditation => {{
            meditation.addEventListener('click', function() {{
                const url = this.getAttribute('data-url');
                if (url) {{
                    window.open(url, '_blank');
                }}
            }});
        }});

        // Initialize on page load
        applyFilters();
    </script>
</body>
</html>
"""

    html = html.format(
        total_count=len(meditations),
        podcast_pills=podcast_pills,
        update_time=datetime.now().strftime('%B %d, %Y at %I:%M %p')
    )

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Generated {output_file} with {len(meditations)} meditations")

def main():
    """
    Main function to process all feeds and generate the webpage.
    """
    # Load feeds configuration
    feeds_file = Path(__file__).parent / 'feeds.json'
    with open(feeds_file, 'r') as f:
        config = json.load(f)

    all_meditations = []

    # Process each feed
    for feed in config['feeds']:
        meditations = parse_feed(feed['url'], feed['name'], feed['website'])
        all_meditations.extend(meditations)

    # Generate HTML
    output_file = Path(__file__).parent / 'index.html'
    generate_html(all_meditations, str(output_file))

    print(f"\nSuccess! Open {output_file} in your browser to view the meditations.")

if __name__ == '__main__':
    main()
