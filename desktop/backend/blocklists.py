"""Fetch a public list of phishing sites for the "Never these sites" guardrail.

The only network call is one GET of the OpenPhish community feed (a text file of phishing page addresses, one per
line). Nothing about the person or their runs is sent. The addresses are cut down to host names, because a run's
block list is by site, not by page.
"""
from __future__ import annotations

import os
import re
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

FEED_URL = "https://openphish.com/feed.txt"
MAX_BYTES = 5_000_000          # the feed is a few tens of kilobytes; this stops anything unexpected
MAX_HOSTS = 3000
TIMEOUT = 20

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOST = re.compile(rf"(?:{_LABEL}\.)+[a-z][a-z0-9-]{{1,62}}")

# Shared platforms. A phishing page can sit on one of these, but blocking the whole host would break pages people
# use every day, so these exact hosts are never added. A page on a subdomain such as scam.example.github.io is
# still blocked, because only that host and anything under it is listed.
SHARED_HOSTS = frozenset("""
google.com docs.google.com drive.google.com sites.google.com forms.gle storage.googleapis.com
github.com githubusercontent.com raw.githubusercontent.com github.io gitlab.io
dropbox.com onedrive.live.com live.com microsoft.com office.com sharepoint.com forms.office.com
amazonaws.com s3.amazonaws.com cloudfront.net azurewebsites.net windows.net
notion.so notion.site medium.com wordpress.com blogspot.com weebly.com wixsite.com
netlify.app vercel.app pages.dev web.app firebaseapp.com herokuapp.com
bit.ly t.co tinyurl.com linktr.ee ipfs.io facebook.com instagram.com twitter.com x.com youtube.com
""".split())


class FeedError(Exception):
    """The list could not be fetched. The message is plain enough to show the person."""


def parse(text: str) -> tuple[list[str], int]:
    """Host names from a feed (one address per line), without repeats, plus how many shared hosts were left out."""
    hosts: dict[str, None] = {}
    skipped = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            host = (urllib.parse.urlparse(line if "//" in line else f"//{line}").hostname or "").lower().rstrip(".")
        except ValueError:
            continue
        if not _HOST.fullmatch(host):
            continue                     # IP addresses, odd names and anything else that is not a host name
        if host in SHARED_HOSTS:
            skipped += 1
            continue
        hosts.setdefault(host)
        if len(hosts) >= MAX_HOSTS:
            break
    return list(hosts), skipped


def _context() -> ssl.SSLContext:
    """Trust the same certificates everywhere, including in the packaged app, which has no system Python."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def fetch_openphish() -> dict[str, Any]:
    """Download the feed. ``SB_OPENPHISH_URL`` points elsewhere (tests)."""
    url = os.environ.get("SB_OPENPHISH_URL") or FEED_URL
    req = urllib.request.Request(url, headers={"User-Agent": "selfbrowse-desktop", "Accept": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_context()) as resp:
            raw = resp.read(MAX_BYTES + 1)
    except Exception as exc:
        raise FeedError(f"Could not reach OpenPhish ({type(exc).__name__}). Check your connection and try again.") from None
    if len(raw) > MAX_BYTES:
        raise FeedError("The list from OpenPhish was larger than expected, so it was not used.")
    hosts, skipped = parse(raw.decode("utf-8", "replace"))
    if not hosts:
        raise FeedError("OpenPhish returned no usable sites, so your list was left as it was.")
    return {"hosts": hosts, "count": len(hosts), "skipped": skipped, "source": "openphish.com",
            "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds")}
