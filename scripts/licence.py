"""Which licence a podcast publishes under, and whether that permits reuse.

This module is a gate, not a note. Feeds are re-checked on every build, and a
feed whose licence is not recognised as open contributes nothing — so if a
publisher changes their terms, the site stops using their recordings on the
next run rather than whenever somebody happens to notice.

Only licences that permit redistribution of the unmodified work for
non-commercial purposes are accepted. The site streams recordings from the
publisher's own servers and reproduces episode descriptions, which needs that
permission; attribution and the licence notice are shown alongside every
recording, which is what the BY term requires in return.
"""

import re

# Ordered most to least restrictive so the first match is the accurate one.
OPEN_LICENCES = [
    {
        "id": "cc-by-nc-nd-4.0",
        "name": "CC BY-NC-ND 4.0",
        "full_name": "Creative Commons Attribution-NonCommercial-NoDerivatives 4.0",
        "url": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
        "patterns": [r"by-nc-nd/4\.0",
                     r"attribution[\s\-]*non-?commercial[\s\-]*no\s*deriv\w*\s*(?:works\s*)?4\.0"],
    },
    {
        "id": "cc-by-nc-nd-3.0",
        "name": "CC BY-NC-ND 3.0",
        "full_name": "Creative Commons Attribution-NonCommercial-NoDerivs 3.0",
        "url": "https://creativecommons.org/licenses/by-nc-nd/3.0/",
        "patterns": [r"by-nc-nd/3\.0", r"by-nc-nd\s*3\.0",
                     r"attribution[\s\-]*non-?commercial[\s\-]*no\s*deriv\w*\s*(?:works\s*)?3\.0"],
    },
    {
        "id": "cc-by-nc-4.0",
        "name": "CC BY-NC 4.0",
        "full_name": "Creative Commons Attribution-NonCommercial 4.0",
        "url": "https://creativecommons.org/licenses/by-nc/4.0/",
        "patterns": [r"by-nc/4\.0", r"attribution[\s\-]*non-?commercial\s*4\.0"],
    },
    {
        "id": "cc-by-sa-4.0",
        "name": "CC BY-SA 4.0",
        "full_name": "Creative Commons Attribution-ShareAlike 4.0",
        "url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "patterns": [r"by-sa/4\.0", r"attribution[\s\-]*share-?alike\s*4\.0"],
    },
    {
        "id": "cc-by-4.0",
        "name": "CC BY 4.0",
        "full_name": "Creative Commons Attribution 4.0",
        "url": "https://creativecommons.org/licenses/by/4.0/",
        "patterns": [r"licenses/by/4\.0", r"creative commons attribution 4\.0"],
    },
]

# Phrases that positively rule a feed out, whatever else the text says.
CLOSED_SIGNALS = [
    r"all rights reserved",
    r"may not be (?:reproduced|redistributed|copied|republished)",
    r"do not (?:redistribute|repost|republish)",
]


def detect_licence(*texts) -> dict:
    """The open licence a feed publishes under, or None if there isn't one.

    None is the safe answer: an unrecognised or missing copyright statement
    means no permission has been granted, so the feed is not used.
    """
    haystack = " ".join(t for t in texts if t).lower()
    if not haystack.strip():
        return None
    for pattern in CLOSED_SIGNALS:
        if re.search(pattern, haystack):
            return None
    for licence in OPEN_LICENCES:
        for pattern in licence["patterns"]:
            if re.search(pattern, haystack):
                return {k: licence[k] for k in ("id", "name", "full_name", "url")}
    return None


def attribution(record: dict, licence: dict) -> str:
    """The credit line for one recording: who made it and who published it.

    The licence name is rendered next to this as a link, so it is deliberately
    not repeated here.
    """
    if not licence:
        return ""
    parts = [p for p in (record.get("teacher"), record.get("feed_name")) if p]
    return " · ".join(dict.fromkeys(parts))
