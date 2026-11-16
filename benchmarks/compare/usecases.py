"""Use cases on real public sites. Read-only, a handful of page loads each. Ground truth is looked up
from the site's own API or pages when a run is judged, so the checks stay right as the sites change."""
from __future__ import annotations

import json
import re
import urllib.request

from tasks import Task, TASKS as _STORE_TASKS

UA = {"User-Agent": "selfbrowse-benchmark (read-only check)"}


def _get(url: str) -> str:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode("utf-8", "replace")


def _github(answer: str, state: dict) -> bool:
    repo = json.loads(_get("https://api.github.com/repos/psf/requests"))
    tag = json.loads(_get("https://api.github.com/repos/psf/requests/releases/latest"))["tag_name"].lstrip("v")
    return "apache" in answer.lower() and tag in answer


def _pypi(answer: str, state: dict) -> bool:
    info = json.loads(_get("https://pypi.org/pypi/httpx/json"))["info"]
    py = re.search(r"\d+\.\d+", info.get("requires_python") or "")
    return info["version"] in answer and bool(py) and py.group() in answer


def _wiki(answer: str, state: dict) -> bool:
    a = answer.lower()
    return "van rossum" in a and "1991" in a


def _books(answer: str, state: dict) -> bool:
    items = []
    for page in (1, 2):
        html = _get(f"https://books.toscrape.com/catalogue/category/books/mystery_3/{'index' if page == 1 else 'page-2'}.html")
        titles = re.findall(r'<h3><a href="[^"]*" title="([^"]+)"', html)
        prices = re.findall(r'price_color">[^\d]*([\d.]+)<', html)
        items += list(zip(titles, prices))
    title, price = min(items, key=lambda x: float(x[1]))
    return price in answer and title[:20].lower() in answer.lower()


def _pydocs(answer: str, state: dict) -> bool:
    return "3.9" in answer


TASKS = [
    Task("U1-github", "GitHub: repository facts",
         "Go to github.com/psf/requests. Tell me the license of the project and the version number of its latest release.",
         _github, live=True),
    Task("U2-pypi", "PyPI: find a package",
         "On pypi.org, find the 'httpx' package. Tell me its latest version and the minimum Python version it requires.",
         _pypi, live=True),
    Task("U3-wikipedia", "Wikipedia: follow an article",
         "Go to en.wikipedia.org, open the article 'Python (programming language)' and tell me who designed the language and in which year it first appeared.",
         _wiki, live=True),
    Task("U4-books", "Scraping sandbox: compare across pages",
         "On books.toscrape.com, open the 'Mystery' category and tell me the title and price of the cheapest book. The category has more than one page, so check them all.",
         _books, live=True),
    Task("U5-pydocs", "Python docs: look up a method",
         "On docs.python.org/3, find the documentation for the str.removeprefix method and tell me which Python version added it.",
         _pydocs, live=True),
    next(t for t in _STORE_TASKS if t.id == "T7-live-hn"),
]


def _gave_a_price(answer: str, state: dict) -> bool:
    """Prices on a travel site change by the minute and need a search engine to verify, so this only checks that the
    agent reported a dollar amount. Whether it is the real cheapest fare has to be judged by looking at the run."""
    return re.search(r"\$\s?\d[\d,]*", answer) is not None


# One real, hard task: a flight search on a site that fights automation. Read-only; nothing is booked.
KAYAK = [
    Task("K1-kayak", "Kayak: cheapest flight COK to ORD for 4",
         "Find the cheapest price of ticket from COK to ORD on Dec 26th for 4 people using kayak ",
         _gave_a_price, live=True),
    # the same search with no site named: the agent picks where to look
    Task("K2-flights", "Cheapest flight COK to ORD for 4 (any site)",
         "Find the cheapest price of ticket from COK to ORD on Dec 26th for 4 people ",
         _gave_a_price, live=True),
]


def _trending_top(answer: str, state: dict) -> bool:
    """The top repository on github.com/trending right now must appear in the answer (looked up when judged)."""
    html = _get("https://github.com/trending")
    m = re.search(r'<h2 class="h3 lh-condensed">\s*<a[^>]*href="/([^"/]+/[^"/]+)"', html)
    return bool(m) and m.group(1).split("/")[1].lower() in answer.lower()


# Showcase prompts for the README: a hard live task, a real-site lookup, and a multi-page comparison.
SHOWCASE = [
    Task("S1-flight-sfo", "Cheapest flight COK to SFO for 4, shortest layover",
         "Find the cheapest price for tickets from COK to SFO on Dec 26th for 4 people. Prefer shortest layover",
         _gave_a_price, live=True),
    Task("S2-trending", "GitHub trending: top repo",
         "Go to github.com/trending and tell me the top repository today, what it does, its star count and its main language.",
         _trending_top, live=True),
    next(t for t in TASKS if t.id == "U4-books"),
    Task("S4-flight-cok", "Cheapest flight ORD to COK for 4, shortest layover",
         "Find the cheapest price for tickets from ORD to COK on Dec 26th for 4 people. Prefer shortest layover",
         _gave_a_price, live=True),
]
