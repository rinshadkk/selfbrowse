"""
Per-site memory: what Selfbrowse has learned about a website, stored as one small JSON file per domain.

Two kinds of knowledge:

* **memo** – short facts the model chose to remember ("search box is #3 on the home page").
* **flows** – click sequences that worked, keyed by a normalised page pattern such as
  ``/*/dp/*``. Each pattern keeps every distinct sequence it has seen (*variants*), and trust is
  worked out for the **start** of a sequence, so a shared first step (a cookie banner) is trusted
  even when what follows differs by task. A start is replayed without calling the model when:

  - **generic**: it succeeded for at least two *different* tasks → replayed for every task;
  - **repeat**: it succeeded at least twice for *this exact* task, whichever way the later clicks
    went → replayed for that task only (a routine job run again and again).

  Repeating one task never makes its incidental clicks look generic. A flow that stops working
  is dropped, and flows unused for 90 days expire.

Only *successful* runs are learned from. Steps after typing, or after a click that changed the page in place (add to cart), are never recorded for it
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

from selfbrowse.guardrails import RISKY_RE as _RISKY

MAX_FLOW_STEPS = 6
MAX_MEMO_FACTS = 12
MAX_FACT_CHARS = 200
MIN_DISTINCT_TASKS = 2          # generic: succeeded for this many different tasks
MIN_SAME_TASK_RUNS = 2          # repeat: succeeded this many times for the same task
MAX_TASKS_KEPT = 20
MAX_VARIANTS = 8                # distinct sequences kept per page pattern
EXPIRE_SECONDS = 90 * 24 * 3600
_RECORDABLE = {"click", "press"}


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


def _upgrade(flow: dict[str, Any]) -> dict[str, Any]:
    """Files written before variants existed held one sequence per pattern; wrap it."""
    if "variants" in flow:
        return flow
    tasks = flow.get("tasks", [])
    runs = flow.get("runs", 1)
    per_task = {k: (runs if len(tasks) == 1 else 1) for k in tasks}
    return {"variants": [{"steps": flow.get("steps", []), "tasks": per_task, "runs": runs, "last": flow.get("last", 0)}],
            "misses": flow.get("misses", 0)}


def _trusted_prefix(variants: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """The longest start of any sequence that is trusted, for this task (``key``)."""
    best: list[dict[str, Any]] = []
    for v in variants:
        steps = v["steps"]
        for k in range(len(steps), len(best), -1):
            prefix = steps[:k]
            sharing = [w for w in variants if w["steps"][:k] == prefix]
            tasks = set().union(*(w["tasks"].keys() for w in sharing))
            mine = sum(w["tasks"].get(key, 0) for w in sharing) if key else 0
            if len(tasks) >= MIN_DISTINCT_TASKS or mine >= MIN_SAME_TASK_RUNS:
                best = prefix
                break
    return best


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
                for pattern, flow in list(data["flows"].items()):
                    data["flows"][pattern] = _upgrade(flow)
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
        """Steps to replay for this page, or [] if there is no trusted start of a flow."""
        flow = self._load(domain_of(url))["flows"].get(normalize_path(url))
        if not flow:
            return []
        now = time.time()
        live = [v for v in flow["variants"] if v.get("steps") and now - v.get("last", 0) <= EXPIRE_SECONDS]
        return list(_trusted_prefix(live, task_key(task) if task else "")) if live else []

    # ── learning (during a run) ────────────────────────────────────────────────
    def record(self, url: str, step: dict[str, Any]) -> None:
        """Remember an action taken on ``url``. Typing seals the page: nothing more is kept for it."""
        domain, pattern = domain_of(url), normalize_path(url)
        sealed = self._sealed.setdefault(domain, set())
        if pattern in sealed:
            return
        if step.get("tool") == "effect":                   # an in-place state change ("Add to cart"): keep what led
            sealed.add(pattern)                            # up to it, learn nothing from it or after it
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
        runs = sum(v.get("runs", 0) for v in flow["variants"])
        if flow["misses"] >= 2 and flow["misses"] > runs // 2:
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
                flow = data["flows"].setdefault(pattern, {"variants": [], "misses": 0})
                same = next((v for v in flow["variants"] if v["steps"] == steps), None)
                if same is None:
                    same = {"steps": steps, "tasks": {}, "runs": 0, "last": 0}
                    flow["variants"].append(same)
                same["runs"] += 1
                same["last"] = time.time()
                if key:
                    same["tasks"][key] = same["tasks"].get(key, 0) + 1
                    while len(same["tasks"]) > MAX_TASKS_KEPT:
                        same["tasks"].pop(next(iter(same["tasks"])))
                flow["variants"] = sorted(flow["variants"], key=lambda v: v["last"])[-MAX_VARIANTS:]
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
