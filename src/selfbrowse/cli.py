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
                   help="provider:model (default: anthropic:claude-haiku-4-5), or your own model as module:Name or ./file.py:Name")
    p.add_argument("--headed", action="store_true", help="show the browser window")
    p.add_argument("--max-steps", type=int, default=100, help="stop after N tool calls (default: 100)")
    p.add_argument("--profile", help="folder to keep cookies/logins between runs")
    p.add_argument("--channel", help="use an installed browser: chrome or msedge")
    p.add_argument("--stealth", action="store_true", help="use Patchright to reduce bot detection")
    rb = p.add_argument_group("remote browser")
    rb.add_argument("--cdp-url", metavar="URL", default=os.environ.get(f"{_about.ENV_PREFIX}CDP_URL"),
                    help="attach to a running browser over CDP (wss://... from a cloud provider, or http://localhost:9222) "
                         "instead of launching one; $SELFBROWSE_CDP_URL also works")
    rb.add_argument("--cdp-header", action="append", default=[], metavar="NAME=VALUE", help="header for the CDP connection (repeatable)")
    rb.add_argument("--cloud", choices=["agentcore"], help="start a session on a managed browser: agentcore = Amazon Bedrock AgentCore (needs selfbrowse[aws])")
    rb.add_argument("--cloud-region", metavar="REGION", help="AWS region for --cloud agentcore (default: $AWS_REGION, else us-east-1)")
    rb.add_argument("--cloud-browser", metavar="ID", help="AgentCore browser id (default: aws.browser.v1)")
    p.add_argument("--page-text", type=int, default=0, metavar="N",
                   help="also send up to N characters of the text on screen with every page list (more tokens, fewer read calls)")
    p.add_argument("--max-output-tokens", type=int, default=2048, metavar="N",
                   help="cap on each model reply (raise for reasoning models that think at length; default 2048)")
    p.add_argument("--vision", action="store_true", help="allow screenshots (more tokens)")
    p.add_argument("--record-video", metavar="DIR",
                   help="record a video of the browser page (WebM) into DIR; saved when the run ends. Not redacted")
    p.add_argument("--screenshots", metavar="DIR",
                   help="save a screenshot after every step, plus an index.html, in a new folder under DIR (evidence; the images are not redacted and are not sent to the model)")
    g = p.add_argument_group("observability")
    g.add_argument("--trace", action="store_true", help="record the run to ~/.selfbrowse/traces/")
    g.add_argument("--show-prompts", action="store_true", help="print every model request to stderr")
    g.add_argument("--trace-hashes", action="store_true", help="trace sizes/hashes instead of prompt text")
    g.add_argument("--otel", metavar="URL", help="export spans to an OTLP/HTTP endpoint, e.g. http://localhost:4318")
    g.add_argument("--otel-content", action="store_true", help="also attach task/prompt text to spans")
    g.add_argument("--full", action="store_true", help="with 'trace show': include full prompts")
    r = p.add_argument_group("guardrails")
    r.add_argument("--allow-domain", action="append", default=[], metavar="DOMAIN", help="only visit these sites (repeatable)")
    r.add_argument("--block-domain", action="append", default=[], metavar="DOMAIN", help="never visit these sites (repeatable)")
    r.add_argument("--confirm-risky", action="store_true", help="ask before buy/pay/delete/send/sign-out clicks")
    r.add_argument("--redact-pii", action="store_true", help="mask emails, phones, SSNs, cards in page text sent to the model")
    r.add_argument("--redact-presidio", action="store_true",
                   help="also mask names and other personal data with Microsoft Presidio (needs selfbrowse[presidio])")
    r.add_argument("--presidio-entities", default="", metavar="LIST",
                   help="Presidio entities to mask, comma-separated (default: person, email, phone, card, ssn, ...)")
    r.add_argument("--presidio-model", default="en_core_web_sm", metavar="NAME",
                   help="spaCy model for Presidio (default en_core_web_sm; en_core_web_lg is more accurate)")
    r.add_argument("--no-restore", action="store_true",
                   help="with --redact-pii/--redact-presidio: mask for good as [email]. By default the model sees "
                        "<EMAIL_1>, the real value is typed back on the same site, and your answer shows the real values")
    r.add_argument("--watch-injection", action="store_true", help="warn on instruction-like page text and confirm risky actions")
    r.add_argument("--max-tokens", type=int, metavar="N", help="stop the run past N total tokens")
    r.add_argument("--max-seconds", type=float, metavar="S", help="stop the run past S seconds")
    p.add_argument("--secret", action="append", default=[], metavar="NAME",
                   help="make a secret available as <secret:NAME>; value comes from $SELFBROWSE_SECRET_NAME, "
                        "or is asked for without echo (repeatable)")
    p.add_argument("--permissions", default="", metavar="LIST",
                   help="grant browser permissions to every site, comma-separated, e.g. notifications,geolocation "
                        "(default: none)")
    p.add_argument("--dialogs", choices=["auto", "accept", "dismiss"], default="auto",
                   help="JavaScript alert/confirm/prompt: auto accepts alerts and declines choices (default)")
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
    if args.task and args.task[0] == "trace":
        return _trace_command(args.task[1:], home / "traces", args.full, p)
    if not args.task:
        p.error("give a task, e.g. selfbrowse \"open example.com and tell me the heading\"")

    secrets = _load_secrets(args.secret, p)

    from selfbrowse.agent import BrowseAgent
    from selfbrowse.browser import Browser, BrowserError
    from selfbrowse.llm import LLMError

    from selfbrowse import guardrails as gr

    guards = gr.build_guards(allow=args.allow_domain, block=args.block_domain, confirm_risky=args.confirm_risky,
                             redact_pii=args.redact_pii, watch_injection=args.watch_injection,
                             max_tokens=args.max_tokens, max_seconds=args.max_seconds,
                             presidio=args.redact_presidio,
                             presidio_entities=[x.strip() for x in args.presidio_entities.split(",") if x.strip()],
                             presidio_model=args.presidio_model, restore=not args.no_restore)
    if args.no_restore and not (args.redact_pii or args.redact_presidio):
        p.error("--no-restore needs --redact-pii or --redact-presidio")
    try:
        for g in guards:
            getattr(g, "check_ready", lambda: None)()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    def show(step) -> None:
        if not args.quiet and not args.json:
            tag = " (learned)" if step.from_cache else ""
            print(f"  {step.number:>2}. {step.tool} {json.dumps(step.input, ensure_ascii=False)}{tag}", file=sys.stderr)

    from selfbrowse.cloud import CloudError, remote_kwargs
    try:
        remote = remote_kwargs(cdp_url=args.cdp_url, headers=args.cdp_header, cloud=args.cloud,
                               region=args.cloud_region, identifier=args.cloud_browser)
    except CloudError as exc:
        p.error(str(exc))
    if remote and (args.record_video or args.profile or args.channel):
        p.error("--record-video, --profile and --channel do not apply to a remote browser (the provider runs it)")
    try:
        browser = Browser(headless=not args.headed, channel=args.channel, user_data_dir=args.profile, stealth=args.stealth,
                          permissions=[x.strip() for x in args.permissions.split(",") if x.strip()], dialogs=args.dialogs, record_video_dir=args.record_video,
                          **remote)
        agent = BrowseAgent(" ".join(args.task), llm=args.model, browser=browser, max_steps=args.max_steps,
                      learn=not args.no_learn, handoff=False if args.no_handoff else "auto", vision=args.vision, screenshots=args.screenshots, page_text=args.page_text, max_output_tokens=args.max_output_tokens, home=home,
                      on_step=show, guardrails=guards, sensitive=secrets, trace=args.trace, show_prompts=args.show_prompts,
                      trace_content=not args.trace_hashes, otel=args.otel, otel_content=args.otel_content)
        try:
            result = agent.run()
            if browser.live_view_url and not args.quiet and not args.json:
                print("  (live view was: " + browser.live_view_url + ")", file=sys.stderr)
        finally:
            browser.close()
    except (LLMError, BrowserError, CloudError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(result.output if result.success else f"FAILED: {result.error or result.output}")
        u = result.usage
        if agent.trace_path:
            print(f"[trace: {agent.trace_path}]", file=sys.stderr)
        if agent.screenshots_dir:
            print(f"[screenshots: {agent.screenshots_dir}]", file=sys.stderr)
        for v in (browser.video_paths() if args.record_video else []):
            print(f"[video: {v}]", file=sys.stderr)
        print(f"[{result.steps} steps, {u.calls} model calls, {u.total_input} in / {u.output_tokens} out tokens]", file=sys.stderr)
    return 0 if result.success else 1


def _load_secrets(names: list[str], parser: argparse.ArgumentParser) -> dict[str, str]:
    """Secrets from SELFBROWSE_SECRET_<NAME> env vars (all of them), plus any --secret NAME asked for without echo."""
    prefix = f"{_about.ENV_PREFIX}SECRET_"
    secrets = {k[len(prefix):]: v for k, v in os.environ.items() if k.startswith(prefix) and len(k) > len(prefix)}
    for name in names:
        if name in secrets:
            continue
        if not sys.stdin.isatty():
            parser.error(f"--secret {name}: set ${prefix}{name}, or run in a terminal to be asked")
        import getpass
        secrets[name] = getpass.getpass(f"Value for secret '{name}' (not shown): ")
    return secrets


def _trace_command(rest: list[str], directory: Path, full: bool, parser: argparse.ArgumentParser) -> int:
    from selfbrowse import trace as tr

    if not rest or rest[0] not in ("list", "show"):
        parser.error("usage: selfbrowse trace list | selfbrowse trace show <run-id|latest> [--full]")
    if rest[0] == "list":
        rows = tr.summarize_dir(directory)
        if not rows:
            print("No traces yet. Run a task with --trace.")
        for r in rows:
            ok = {True: "ok  ", False: "FAIL", None: "?   "}[r["success"]]
            print(f"{r['id']}  {ok} {r['calls']} calls  {r['tokens'] or '?':>7} tokens  {str(r['task'])[:60]}")
        return 0
    path = tr.find(directory, rest[1] if len(rest) > 1 else "latest")
    if not path:
        print("no such trace", file=sys.stderr)
        return 1
    print(tr.render(tr.load(path), full=full))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
