"""Benchmark tasks and their success checks. Success is judged here, never by the agent's own claim."""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable


@dataclass
class Task:
    id: str
    title: str
    prompt: str                    # may contain {base}
    check: Callable[[str, dict], bool]
    live: bool = False


def _hn_top_title() -> str:
    try:
        top = json.load(urllib.request.urlopen("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=15))[0]
        return json.load(urllib.request.urlopen(f"https://hacker-news.firebaseio.com/v0/item/{top}.json", timeout=15)).get("title", "")
    except Exception:
        return ""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def _hn_check(answer: str, state: dict) -> bool:
    title = state.get("hn_before", "") or ""
    after = state.get("hn_after", "") or ""
    a = _norm(answer)
    return any(t and _norm(t)[:30] in a for t in (title, after))


TASKS = [
    Task("T1-read-text", "Read a fact from a text page",
         "Open {base}/about and tell me in which year Demo Store was founded.",
         lambda a, s: "1987" in a),
    Task("T2-search", "Search and compare",
         "Go to {base}, search for 'kettle' and tell me the price of the cheapest kettle.",
         lambda a, s: "24.99" in a),
    Task("T3-navigate", "Multi-page navigation",
         "Open {base}, go to the Garden category, open the product 'Trowel Set' and tell me how many are in stock.",
         lambda a, s: re.search(r"\b12\b", a) is not None),
    Task("T4-cart", "Action behind a cookie banner",
         "On {base}, add the 'Desk Lamp' to the cart. Then say done.",
         lambda a, s: s.get("cart") == {"4": 1}),
    Task("T5-login", "Log in and read",
         "Log in at {base}/login with username 'alice' and password 'pw-1234', then tell me the full name shown on the welcome page.",
         lambda a, s: bool(s.get("login")) and "alice anderson" in a.lower()),
    Task("T6-paginate", "Find an item across pages",
         "On {base}/list, find the item with SKU ZX-4471 and tell me its name.",
         lambda a, s: "brass hinge" in a.lower()),
    Task("T7-live-hn", "Live: Hacker News top story",
         "Open news.ycombinator.com and tell me the title of the top story.",
         _hn_check, live=True),
    Task("T8-live-wiki", "Live: Wikipedia fact",
         "Go to en.wikipedia.org, find the article 'Web browser' and tell me in which year the first web browser was created.",
         lambda a, s: "1990" in a, live=True),
]
