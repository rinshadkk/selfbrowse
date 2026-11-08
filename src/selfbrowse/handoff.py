"""
Hand the browser to a person when the agent cannot go further.

Two triggers:

* **Automatic**: the page looks like a bot check (CAPTCHA, "verify you are human", "press and
  hold", Cloudflare "Just a moment"...). Selfbrowse never tries to solve these itself.
* **On request**: the model calls ``ask_human`` for things only a person can do (sign in without
  a stored secret, a 2FA code, a payment step, an ambiguous choice).

A *handler* gets a :class:`HandoffRequest`, lets the person act in the (visible) browser
window, and returns ``True`` to resume or ``False`` to give up. The default handler asks in the
terminal; pass your own ``handoff=`` callable to use anything else.

Nothing the person types or sees is sent to the model; it is only told that they finished.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Callable


@dataclass
class HandoffRequest:
    kind: str       # "challenge" (detected automatically), "model" (the model asked) or "confirm" (a guardrail
                    # wants approval: return True to allow the action, False to deny it)
    reason: str     # short human-readable explanation
    url: str


Handler = Callable[[HandoffRequest], bool]

_TITLE = re.compile(
    r"just a moment|attention required|access denied|robot or human|are you a robot|"
    r"security check|verify you are human|pardon our interruption|human verification",
    re.I,
)
_TEXT = re.compile(
    r"verify (that )?you(?:'|’)?re (a )?human|verify you are (a )?human|are you a (robot|human)|"
    r"press (&|and) hold|unusual traffic|checking (if the site connection is secure|your browser)|"
    r"prove you(?:'|’)?re (not a robot|human)|i(?:'|’)?m not a robot|complete the (captcha|security check)|"
    r"robot or human|confirm you are (a )?human|verifying you are human|"
    r"enable javascript and cookies to continue|captcha",
    re.I,
)
_MAX_ELEMENTS_FOR_TEXT_MATCH = 30      # a real article that merely mentions CAPTCHAs has many more controls


def detect_block(title: str, text: str, n_elements: int) -> str | None:
    """Return a short reason if the page looks like a bot check, else None."""
    if _TITLE.search(title or ""):
        return "the site is showing a bot check or access block"
    if n_elements <= _MAX_ELEMENTS_FOR_TEXT_MATCH and _TEXT.search(text or ""):
        return "the site is asking to verify you are human"
    return None


def terminal_handler(req: HandoffRequest, timeout: float = 900.0) -> bool:
    """Ask in the terminal. Enter = resume, q = give up. Declines when there is no terminal."""
    if not sys.stdin or not sys.stdin.isatty():
        return False
    err = sys.stderr
    if req.kind == "confirm":
        ask = "│ Approve this action? Enter = yes, n + Enter = no.\n"
        title = "Selfbrowse asks permission"
    else:
        ask = ("│ Do it in the browser window, then press Enter here to continue\n"
               "│ (type q + Enter to give up).\n")
        title = "Selfbrowse needs you"
    err.write(
        "\a\n"
        f"┌─ {title} ─────────────────────────────\n"
        f"│ {req.reason}\n"
        f"│ {req.url}\n"
        f"{ask}"
        "└────────────────────────────────────────────────────\n"
    )
    err.flush()
    try:
        import select
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            err.write("(no answer, giving up)\n")
            return False
    except (ImportError, OSError, ValueError):       # e.g. select on stdin is unsupported (Windows)
        pass
    return sys.stdin.readline().strip().lower() not in {"q", "quit", "n", "no"}
