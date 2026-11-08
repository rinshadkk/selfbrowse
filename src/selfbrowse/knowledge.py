"""
Per-site memory: what Selfbrowse has learned about a website, stored as one small JSON file per domain.

Two kinds of knowledge:

* **memo** – short facts the model chose to remember ("search box is #3 on the home page").
* **flows** – click sequences that worked, keyed by a normalised page pattern such as
  ``/*/dp/*``. They are replayed without calling the model, but only when trusted:

  - **generic**: the same flow succeeded for at least two *different* tasks (a cookie banner, a
    sign-in step) → replayed for every task;
  - **repeat**: the same flow succeeded at least twice for *this exact* task → replayed for that
    task only (a routine job run again and again).

  Repeating one task never makes its incidental clicks look generic. A flow that stops working
  is dropped, and flows unused for 90 days expire.

Only *successful* runs are learned from. Steps after typing on a page are never recorded for it
(what was typed is task-specific), and risky clicks (buy, delete, send, sign out...) are never
recorded at all.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MAX_FLOW_STEPS = 6
MAX_MEMO_FACTS = 12
MAX_FACT_CHARS = 200
MIN_DISTINCT_TASKS = 2          # generic: succeeded for this many different tasks
MIN_SAME_TASK_RUNS = 2          # repeat: succeeded this many times for the same task
MAX_TASKS_KEPT = 20
EXPIRE_SECONDS = 90 * 24 * 3600
_RECORDABLE = {"click", "press"}
_RISKY = re.compile(
    r"\b(buy|purchase|pay|checkout|check out|place order|order now|confirm|delete|remove|cancel|"
    r"unsubscribe|send|submit|post|publish|sign out|log ?out|subscribe|donate|transfer|withdraw)\b",
    re.I,
)


def task_key(task: str) -> str:
    """Stable id for a task, ignoring case and spacing."""
    return hashlib.sha1(" ".join(task.lower().split()).encode()).hexdigest()[:12]


def normalize_path(url: str) -> str:
    """``/Some-Product-Name/dp/B0ABC123`` → ``/*/dp/*`` so one entry covers a whole page type."""
    segs = [s for s in urlparse(url).path.split("/") if s]
    out = ["*" if _looks_variable(s) else s.lower() for s in segs[:6]]
    return "/" + "/".join(out)


def _looks_variable(seg: str) -> bool:
    return (
        any(c.isdigit() for c in seg)
        or seg.count("-") >= 2
        or seg.count("_") >= 2
        or len(seg) > 24
        or bool(re.fullmatch(r"[0-9a-f]{8,}", seg, re.I))
    )


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


class SiteKnowledge:
    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory).expanduser()
        self._pending: dict[str, dict[str, list[dict[str, Any]]]] = {}   # domain → pattern → steps
        self._sealed: dict[str, set[str]] = {}
        self._pending_memo: dict[str, list[str]] = {}

    # ── storage ────────────────────────────────────────────────────────────────
    def _file(self, domain: str) -> Path:
        safe = re.sub(r"[^a-z0-9.-]", "_", domain.lower())[:100] or "unknown"
        return self.dir / f"{safe}.json"

    def _load(self, domain: str) -> dict[str, Any]:
        try:
            data = json.loads(self._file(domain).read_text())
            if isinstance(data, dict):
                data.setdefault("memo", [])
                data.setdefault("flows", {})
                return data
        except (OSError, ValueError):
            pass
        return {"memo": [], "flows": {}}

    def _save(self, domain: str, data: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, indent=1)
            os.replace(tmp, self._file(domain))
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # ── reading ────────────────────────────────────────────────────────────────
    def get_memo(self, url: str) -> list[str]:
        return list(self._load(domain_of(url))["memo"])

    def get_steps(self, url: str, task: str = "") -> list[dict[str, Any]]:
        """Steps to replay for this page, or [] if there is no trusted flow."""
        flow = self._load(domain_of(url))["flows"].get(normalize_path(url))
        if not flow or not flow.get("steps"):
            return []
        if time.time() - flow.get("last", 0) > EXPIRE_SECONDS:
            return []
        tasks = flow.get("tasks", [])
        generic = len(tasks) >= MIN_DISTINCT_TASKS
        repeat = bool(task) and task_key(task) in tasks and flow.get("runs", 0) >= MIN_SAME_TASK_RUNS
        return list(flow["steps"]) if generic or repeat else []

    # ── learning (during a run) ────────────────────────────────────────────────
    def record(self, url: str, step: dict[str, Any]) -> None:
        """Remember an action taken on ``url``. Typing seals the page: nothing more is kept for it."""
        domain, pattern = domain_of(url), normalize_path(url)
        sealed = self._sealed.setdefault(domain, set())
        if pattern in sealed:
            return
        if step.get("tool") == "type":
            sealed.add(pattern)
            self._pending.get(domain, {}).pop(pattern, None)
            return
        if step.get("tool") == "click" and _RISKY.search(step.get("text", "")):
            sealed.add(pattern)                        # never learn past a risky control
            self._pending.get(domain, {}).pop(pattern, None)
            return
        if step.get("tool") in _RECORDABLE:
            self._pending.setdefault(domain, {}).setdefault(pattern, []).append(step)

    def undo_last(self, url: str) -> None:
        """The agent went back to ``url``: the click that left it was a detour, so forget it."""
        steps = self._pending.get(domain_of(url), {}).get(normalize_path(url))
        if steps:
            steps.pop()

    def remember(self, url: str, fact: str) -> None:
        fact = " ".join(fact.split())[:MAX_FACT_CHARS]
        if fact:
            self._pending_memo.setdefault(domain_of(url), []).append(fact)

    def record_miss(self, url: str) -> None:
        """A replayed flow failed; forget it after repeated failures."""
        domain, pattern = domain_of(url), normalize_path(url)
        data = self._load(domain)
        flow = data["flows"].get(pattern)
        if not flow:
            return
        flow["misses"] = flow.get("misses", 0) + 1
        if flow["misses"] >= 2 and flow["misses"] > flow.get("runs", 0) // 2:
            del data["flows"][pattern]
        self._save(domain, data)

    # ── learning (after a run) ─────────────────────────────────────────────────
    def commit(self, success: bool, task: str = "") -> None:
        """Persist what was learned. Failed runs teach nothing."""
        pending, memos = self._pending, self._pending_memo
        self._pending, self._pending_memo, self._sealed = {}, {}, {}
        if not success:
            return
        for domain in set(pending) | set(memos):
            data = self._load(domain)
            key = task_key(task) if task else ""
            for pattern, steps in pending.get(domain, {}).items():
                if not steps or len(steps) > MAX_FLOW_STEPS:
                    continue
                old = data["flows"].get(pattern)
                if old and old.get("steps") == steps:
                    old["runs"] = old.get("runs", 0) + 1
                    old["last"] = time.time()
                    if key and key not in old.setdefault("tasks", []):
                        old["tasks"] = (old["tasks"] + [key])[-MAX_TASKS_KEPT:]
                else:
                    data["flows"][pattern] = {"steps": steps, "tasks": [key] if key else [],
                                              "runs": 1, "misses": 0, "last": time.time()}
            for fact in memos.get(domain, []):
                if fact not in data["memo"]:
                    data["memo"].append(fact)
            data["memo"] = data["memo"][-MAX_MEMO_FACTS:]
            self._save(domain, data)

    # ── housekeeping (CLI) ─────────────────────────────────────────────────────
    def domains(self) -> list[str]:
        return sorted(p.stem for p in self.dir.glob("*.json")) if self.dir.exists() else []

    def forget(self, domain: str) -> bool:
        f = self._file(domain.lower().removeprefix("www."))
        if f.exists():
            f.unlink()
            return True
        return False
