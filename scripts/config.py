"""Site-wide constants and taxonomies.

Everything that is a *policy* decision — how long a "10-minute" meditation is,
which analytics provider is used, how many cards a page holds — lives here, so
the rest of the pipeline stays mechanical.
"""

from pathlib import Path

# --- Identity --------------------------------------------------------------

SITE_URL = "https://alastairrushworth.com/meditation/"
SITE_NAME = "Guided Meditations"
SITE_TAGLINE = "A curated collection from dharma podcasts"
AUTHOR_NAME = "Alastair Rushworth"
AUTHOR_URL = "https://alastairrushworth.com"
REPO_URL = "https://github.com/alastairrushworth/meditation"
LOCALE = "en_GB"
LANG = "en-GB"

# --- Analytics -------------------------------------------------------------
# Cookieless by choice: no consent banner is needed, and nothing personal is
# stored. Plausible identifies a site by its domain alone, so no key is needed
# here — add the domain in the Plausible dashboard and data starts flowing.
# Set PROVIDER to None to ship no analytics at all.
ANALYTICS = {
    "provider": "plausible",
    "domain": "alastairrushworth.com",
    "src": "https://plausible.io/js/script.js",
}

# --- Paths -----------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent
SITE_ROOT = SCRIPTS_DIR.parent
TEMPLATE_DIR = SCRIPTS_DIR / "templates"
FEEDS_FILE = SCRIPTS_DIR / "feeds.json"
ARCHIVE_FILE = SITE_ROOT / "data" / "meditations.json"
ASSETS_DIR = SITE_ROOT / "assets"

# --- Fetching --------------------------------------------------------------

USER_AGENT = (
    "GuidedMeditationsBot/1.0 (+https://alastairrushworth.com/meditation/; "
    "static site generator; contact via GitHub)"
)
FETCH_TIMEOUT = 90
FETCH_RETRIES = 3
FETCH_BACKOFF = 2.0

# A build is abandoned rather than published if too much of the source data is
# missing — a degraded site is worse than a stale one. See store.guard_build.
MAX_FAILED_FEED_FRACTION = 0.25

# --- Page sizing -----------------------------------------------------------

PAGE_SIZE = 40              # meditations per page of the archive
FEED_ITEMS = 60             # items in the site's own RSS feed

# --- Duration buckets ------------------------------------------------------
# `short` is the label in the length filter. `max_seconds` is inclusive; the
# last bucket catches everything above.

LENGTH_BUCKETS = [
    {"slug": "10-minutes", "max_seconds": 12 * 60,
     "short": "About 10 minutes"},
    {"slug": "15-minutes", "max_seconds": 18 * 60,
     "short": "About 15 minutes"},
    {"slug": "20-minutes", "max_seconds": 25 * 60,
     "short": "About 20 minutes"},
    {"slug": "30-minutes", "max_seconds": 38 * 60,
     "short": "About 30 minutes"},
    {"slug": "45-minutes", "max_seconds": 52 * 60,
     "short": "About 45 minutes"},
    {"slug": "60-minutes", "max_seconds": None,
     "short": "An hour or more"},
]

# --- Practice taxonomy -----------------------------------------------------
# Ordered by specificity: the first match wins for a card's primary label, but
# an episode can match several. `short` is the label in the practice filter.

PRACTICES = [
    {"slug": "body-scan",
     "short": "Body scan",
     "keywords": ["body scan", "bodyscan", "body-scan", "scanning the body"]},
    {"slug": "loving-kindness",
     "short": "Loving-kindness",
     "keywords": ["metta", "loving-kindness", "lovingkindness",
                  "loving kindness", "friendliness practice"]},
    {"slug": "compassion",
     "short": "Compassion",
     "keywords": ["compassion", "karuna", "tonglen", "self-compassion"]},
    {"slug": "equanimity",
     "short": "Equanimity",
     "keywords": ["equanimity", "upekkha", "upekha"]},
    {"slug": "gratitude-and-joy",
     "short": "Gratitude & joy",
     "keywords": ["gratitude", "mudita", "sympathetic joy", "appreciative joy",
                  "grateful"]},
    {"slug": "breath",
     "short": "Breath",
     "keywords": ["breath", "breathing", "anapana", "anapanasati"]},
    {"slug": "open-awareness",
     "short": "Open awareness",
     "keywords": ["open awareness", "choiceless", "spacious awareness",
                  "open monitoring", "natural awareness", "resting in awareness",
                  "awake awareness"]},
    {"slug": "walking",
     "short": "Walking",
     "keywords": ["walking meditation", "walking practice", "standing meditation"]},
    {"slug": "rest-and-sleep",
     "short": "Rest & sleep",
     "keywords": ["sleep", "yoga nidra", "relaxation", "deep rest",
                  "restful awareness", "letting go into rest"]},
    {"slug": "difficult-emotions",
     "short": "Difficult emotions",
     "keywords": ["anxiety", "fear", "anger", "grief", "difficult emotion",
                  "difficult feelings", "pain", "shame", "loneliness",
                  "working with emotions", "rain "]},
    {"slug": "concentration",
     "short": "Concentration",
     "keywords": ["samadhi", "concentration", "jhana", "collectedness",
                  "unification"]},
]

