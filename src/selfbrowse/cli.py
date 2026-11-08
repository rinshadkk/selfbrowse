"""Command line: ``selfbrowse "find the top story on Hacker News"``."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from selfbrowse import __version__, _about


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=_about.NAME, description="Run a browser task described in plain language.")
    p.add_argument("task", nargs="*", help='the task, or "sites" / "forget <domain>"')
    p.add_argument("-m", "--model", default=os.environ.get(f"{_about.ENV_PREFIX}MODEL", "anthropic:claude-haiku-4-5"),
                   help="provider:model (default: anthropic:claude-haiku-4-5)")
    p.add_argument("--headed", action="store_true", help="show the browser window")
    p.add_argument("--max-steps", type=int, default=25)
    p.add_argument("--profile", help="folder to keep cookies/logins between runs")
    p.add_argument("--channel", help="use an installed browser: chrome or msedge")
    p.add_argument("--stealth", action="store_true", help="use Patchright to reduce bot detection")
    p.add_argument("--vision", action="store_true", help="allow screenshots (more tokens)")
    p.add_argument("--no-handoff", action="store_true", help="never pause for a person (CAPTCHA, login, 2FA)")
    p.add_argument("--no-learn", action="store_true", help="do not read or write site knowledge")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    p.add_argument("-q", "--quiet", action="store_true", help="do not print each step")
    p.add_argument("--version", action="version", version=f"{_about.NAME} {__version__}")
    args = p.parse_args(argv)

    home = Path(os.environ.get(f"{_about.ENV_PREFIX}HOME") or Path.home() / _about.HOME_DIRNAME)

    if args.task and args.task[0] == "sites":
        from selfbrowse.knowledge import SiteKnowledge
        domains = SiteKnowledge(home / "sites").domains()
        print("\n".join(domains) if domains else "No sites learned yet.")
        return 0
    if args.task and args.task[0] == "forget":
        from selfbrowse.knowledge import SiteKnowledge
        if len(args.task) < 2:
            p.error("usage: selfbrowse forget <domain>")
        print("forgot" if SiteKnowledge(home / "sites").forget(args.task[1]) else "nothing stored for that domain")
        return 0
    if not args.task:
        p.error("give a task, e.g. selfbrowse \"open example.com and tell me the heading\"")

    from selfbrowse.agent import Agent
    from selfbrowse.browser import Browser, BrowserError
    from selfbrowse.llm import LLMError

    def show(step) -> None:
        if not args.quiet and not args.json:
            tag = " (learned)" if step.from_cache else ""
            print(f"  {step.number:>2}. {step.tool} {json.dumps(step.input, ensure_ascii=False)}{tag}", file=sys.stderr)

    try:
        browser = Browser(headless=not args.headed, channel=args.channel, user_data_dir=args.profile, stealth=args.stealth)
        agent = Agent(" ".join(args.task), llm=args.model, browser=browser, max_steps=args.max_steps,
                      learn=not args.no_learn, handoff=False if args.no_handoff else "auto", vision=args.vision, home=home, on_step=show)
        try:
            result = agent.run()
        finally:
            browser.close()
    except (LLMError, BrowserError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(result.output if result.success else f"FAILED: {result.error or result.output}")
        u = result.usage
        print(f"[{result.steps} steps, {u.calls} model calls, {u.total_input} in / {u.output_tokens} out tokens]", file=sys.stderr)
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
