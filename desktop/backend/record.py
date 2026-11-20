"""What each model call sent and received, for the "Sent to model" view.

The record is made from the exact ``system`` / ``messages`` the agent passes to the model, so it shows what
left the computer, not a description of it. Each message is stored once per run (by hash) and calls refer
to messages by id, so a long run does not repeat its whole history in every call.

The scan is a safety net, not a redactor: it points out text in what was sent that looks personal
(an email, a phone number, a card number) or matches a value in My info. Selfbrowse's own protection is the
``<secret:NAME>`` mechanism; the scan tells the person when something got past it.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

MAX_TEXT = 20_000            # per message; longer text is cut and marked
SECRET_REF = re.compile(r"<secret:([A-Za-z0-9_]+)>")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\w.])(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?![\w.])")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def _luhn(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if flip:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total, flip = total + d, not flip
    return total % 10 == 0


def _blocks_text(content: Any) -> str:
    """Flatten one message's content to the text the model actually receives."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for b in content or []:
        if not isinstance(b, dict):
            parts.append(str(b))
        elif b.get("type") == "text":
            parts.append(str(b.get("text", "")))
        elif b.get("type") == "tool_use":
            parts.append(f"{b.get('name')} {json.dumps(b.get('input', {}), ensure_ascii=False)}")
        elif b.get("type") == "tool_result":
            parts.append(_blocks_text(b.get("content")))
        elif b.get("type") == "image":
            parts.append("[a screenshot of the page was sent as an image]")
        else:
            parts.append(f"[{b.get('type', 'block')}]")
    return "\n".join(p for p in parts if p)


_PRESIDIO: Any = None
PRESIDIO_MIN_SCORE = 0.5
# Entity types worth flagging. Presidio also finds things like URLs and dates that are everywhere on a web page.
PRESIDIO_ENTITIES = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "US_PASSPORT",
                     "US_DRIVER_LICENSE", "US_BANK_NUMBER", "IBAN_CODE", "IP_ADDRESS", "MEDICAL_LICENSE", "CRYPTO"]


PRESIDIO_MODEL = "en_core_web_sm"        # small (12 MB); Presidio's own default is the 400 MB large one


def presidio_available() -> bool:
    import importlib.util
    return all(importlib.util.find_spec(m) is not None for m in ("presidio_analyzer", PRESIDIO_MODEL))


def _presidio_scan(text: str) -> list[dict[str, str]]:
    """Personal data found by Microsoft Presidio (names, ID numbers, ...). Runs on this computer, loaded once."""
    global _PRESIDIO
    if _PRESIDIO is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        nlp = NlpEngineProvider(nlp_configuration={"nlp_engine_name": "spacy",
                                                   "models": [{"lang_code": "en", "model_name": PRESIDIO_MODEL}]})
        _PRESIDIO = AnalyzerEngine(nlp_engine=nlp.create_engine(), supported_languages=["en"])
    out = []
    for r in _PRESIDIO.analyze(text=text, language="en", entities=PRESIDIO_ENTITIES):
        if r.score >= PRESIDIO_MIN_SCORE:
            out.append({"kind": "pii", "name": r.entity_type.replace("_", " ").lower(), "match": text[r.start:r.end]})
    return out


def scan(text: str, secrets: dict[str, str], presidio: bool = False) -> list[dict[str, str]]:
    """Things in ``text`` the person may not want to have sent. Each finding names the exact text found."""
    found: dict[tuple[str, str], dict[str, str]] = {}
    for name, value in secrets.items():
        if len(value) >= 3 and value in text:
            found[("value", value)] = {"kind": "value", "name": name, "match": value}
    for m in EMAIL.finditer(text):
        found.setdefault(("email", m.group()), {"kind": "email", "name": "email address", "match": m.group()})
    for m in CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            found.setdefault(("card", m.group().strip()), {"kind": "card", "name": "card number", "match": m.group().strip()})
    for m in PHONE.finditer(text):
        if not any(m.group() in k[1] for k in found if k[0] in ("card", "value")):
            found.setdefault(("phone", m.group()), {"kind": "phone", "name": "phone number", "match": m.group()})
    if presidio:
        for f in _presidio_scan(text):
            if not any(f["match"] in k[1] or k[1] in f["match"] for k in found):      # already flagged by a pattern
                found.setdefault(("pii", f["match"]), f)
    return list(found.values())


def build(kwargs: dict[str, Any], table: dict[str, dict[str, Any]], secrets: dict[str, str],
          presidio: bool = False) -> dict[str, Any]:
    """The payload of one call. New messages are added to ``table`` and returned under ``new``."""
    system = kwargs.get("system") or []
    sys_text = "\n".join(b.get("text", "") for b in system if isinstance(b, dict)) if isinstance(system, list) else str(system)
    rows = [("system", sys_text)] + [(m.get("role", "?"), _blocks_text(m.get("content"))) for m in kwargs.get("messages", [])]
    ids: list[str] = []
    new: dict[str, dict[str, Any]] = {}
    for role, text in rows:
        cut = len(text) > MAX_TEXT
        text = text[:MAX_TEXT]
        mid = hashlib.sha1(f"{role}\0{text}".encode()).hexdigest()[:12]
        ids.append(mid)
        if mid not in table:
            entry: dict[str, Any] = {"role": role, "text": text, "cut": cut,
                                     "refs": sorted(set(SECRET_REF.findall(text))),
                                     "flags": scan(text, secrets, presidio) if role in ("user", "system") else []}
            table[mid] = entry
            new[mid] = entry
    return {"ids": ids, "new": new, "tools": [t.get("name", "?") for t in kwargs.get("tools", [])]}


def reply_text(response: Any) -> str:
    return _blocks_text(getattr(response, "content", None))


def usage_of(response: Any) -> dict[str, int]:
    u = getattr(response, "usage", None)
    return {"input": getattr(u, "input_tokens", 0), "cache_read": getattr(u, "cache_read_tokens", 0),
            "cache_write": getattr(u, "cache_write_tokens", 0), "output": getattr(u, "output_tokens", 0)}
