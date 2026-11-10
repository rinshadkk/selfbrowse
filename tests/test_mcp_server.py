"""The MCP server, driven through a real MCP client against the fixture pages."""
import asyncio
import sys

import pytest

pytest.importorskip("mcp")

from mcp.client import Client                      # noqa: E402

from selfbrowse import Browser                      # noqa: E402
from selfbrowse.mcp_server import ServerConfig, create_server, parse_args   # noqa: E402
from tests.conftest import ScriptedLLM              # noqa: E402

pytestmark = pytest.mark.browser


def text_of(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


def ref_of(text: str, needle: str) -> int:
    return next(int(l.split()[0][1:]) for l in text.splitlines() if l.startswith("#") and needle in l)


async def call(client, tool, **args):
    return await client.call_tool(tool, args)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def served(site):
    """(server, browser) with a real browser; yields a helper to open a client."""
    made = []

    def make(cfg=None, **kw):
        browser = Browser()
        server = create_server(cfg or ServerConfig(**kw), browser=browser)
        made.append(server)
        return server

    yield make
    for s in made:
        s.selfbrowse_session.close()


def test_lists_both_kinds_of_tools(served):
    async def go():
        async with Client(served()) as c:
            return {t.name for t in (await c.list_tools()).tools}
    names = run(go())
    assert {"browse", "browser_snapshot", "browser_click", "browser_type", "browser_select", "browser_find",
            "browser_switch_tab", "browser_goto", "browser_read"} <= names


def test_modes_can_be_limited(served):
    async def go(modes):
        async with Client(served(modes=modes)) as c:
            return {t.name for t in (await c.list_tools()).tools}
    assert run(go(("step",))) == run(go(("step",))) and "browse" not in run(go(("step",)))
    assert run(go(("task",))) == {"browse"}


def test_step_mode_drives_a_dropdown_form(served, site):
    async def go():
        async with Client(served()) as c:
            await call(c, "browser_goto", url=site("form.html"))
            snap = text_of(await call(c, "browser_snapshot"))
            assert 'combobox "Country"' in snap and "options:" in snap
            out = text_of(await call(c, "browser_select", ref=ref_of(snap, "Country"), option="France"))
            assert 'selected "France"' in out and "--- page ---" in out
            return text_of(await call(c, "browser_read"))
    assert "country=fr" in run(go())


def test_find_and_tabs(served, site):
    async def go():
        async with Client(served()) as c:
            await call(c, "browser_goto", url=site("tabs.html"))
            snap = text_of(await call(c, "browser_snapshot"))
            out = text_of(await call(c, "browser_click", ref=ref_of(snap, "Open details")))
            assert '[tabs: 1 "Tabs home" · 2 "Details tab" (current)]' in out
            assert "4821" in text_of(await call(c, "browser_read"))
            back = text_of(await call(c, "browser_close_tab"))
            assert "closed tab 2" in back and "[tabs:" not in back
            await call(c, "browser_goto", url=site("long.html"))
            return text_of(await call(c, "browser_find", text="returns are free"))
    assert "match 1 of 1" in run(go())


def test_guardrails_block_other_sites_and_risky_clicks(served, site):
    async def go():
        cfg = ServerConfig(allow_domains=["127.0.0.1"], block_risky=True)
        async with Client(served(cfg)) as c:
            out = text_of(await call(c, "browser_goto", url="https://example.com"))
            assert "Blocked by guardrail AllowedDomains" in out
            await call(c, "browser_goto", url=site("contact.html"))
            snap = text_of(await call(c, "browser_snapshot"))
            blocked = text_of(await call(c, "browser_click", ref=ref_of(snap, "Delete account")))
            assert "Needs a person's approval, so blocked by guardrail ConfirmRisky" in blocked
            assert "deleted" not in text_of(await call(c, "browser_read"))      # the click really did not happen
            return out
    run(go())


def test_secrets_are_substituted_but_never_shown(served, site):
    async def go():
        cfg = ServerConfig(secrets={"pw": "hunter2"})
        async with Client(served(cfg)) as c:
            await call(c, "browser_goto", url=site("shop.html"))
            snap = text_of(await call(c, "browser_snapshot"))
            ref = ref_of(snap, "Password")
            out = text_of(await call(c, "browser_type", ref=ref, text="<secret:pw>"))
            assert "hunter2" not in out
            bad = text_of(await call(c, "browser_type", ref=ref, text="<secret:nope>"))
            assert "Unknown secret" in bad and "hunter2" not in bad
        return served  # noqa
    run(go())


def test_browse_task_mode_returns_only_the_answer(served, site):
    llm = ScriptedLLM([("goto", {"url": "PLACEHOLDER"}), ("read", {}), ("done", {"success": True, "answer": "four eight two one"})])

    async def go():
        llm.script[0] = ("goto", {"url": site("tabs_new.html")})
        cfg = ServerConfig(llm=llm, learn=False)
        async with Client(served(cfg)) as c:
            return await call(c, "browse", task="Open the details page and tell me the code")
    res = run(go())
    out = text_of(res)
    assert not res.is_error and out.startswith("four eight two one")
    assert "3 steps" in out or "steps" in out and "tokens" in out
    assert "4821" not in out                          # the page content stayed inside Selfbrowse


def test_browse_reports_failure_as_a_tool_error(served, site):
    llm = ScriptedLLM([("done", {"success": False, "answer": "could not find it"})] * 2)

    async def go():
        async with Client(served(ServerConfig(llm=llm, learn=False))) as c:
            return await call(c, "browse", task="Find the unicorn")
    res = run(go())
    assert res.is_error and "could not" in text_of(res).lower()


def test_browse_without_a_model_says_how_to_fix_it(served):
    async def go():
        async with Client(served(ServerConfig())) as c:
            return await call(c, "browse", task="anything")
    res = run(go())
    assert res.is_error and "--model" in text_of(res)


def test_parse_args_reads_flags_and_secret_env(monkeypatch):
    monkeypatch.setenv("SELFBROWSE_SECRET_login", "abc")
    assert ServerConfig().max_steps == 100
    assert parse_args([]).max_steps == 100
    cfg = parse_args(["--model", "ollama:qwen3.6", "--allow-domain", "a.com", "--headed", "--modes", "step", "--block-risky"])
    assert (cfg.model, cfg.allow_domains, cfg.headed, cfg.modes, cfg.block_risky) == ("ollama:qwen3.6", ["a.com"], True, ("step",), True)
    assert cfg.secrets == {"login": "abc"}
    with pytest.raises(SystemExit):
        parse_args(["--modes", "nonsense"])


def test_real_stdio_process_speaks_mcp_and_keeps_stdout_clean(site):
    """Start the actual command, as VS Code or Claude Code would, and list its tools over stdio."""
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp import ClientSession

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "selfbrowse.mcp_server", "--modes", "step"])
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = (await s.list_tools()).tools
                out = await s.call_tool("browser_goto", {"url": site("tabs_new.html")})
                return {t.name for t in tools}, "".join(getattr(c, "text", "") for c in out.content)
    names, out = run(go())
    assert "browser_snapshot" in names and "browse" not in names
    assert "Details" in out and "--- page ---" in out


def test_step_mode_reports_dialogs_and_guardrails_veto_risky_accepts(site):
    browser = Browser(dialogs="accept")
    server = create_server(ServerConfig(block_risky=True), browser=browser)

    async def go():
        async with Client(server) as c:
            await call(c, "browser_goto", url=site("dialogs.html"))
            snap = text_of(await call(c, "browser_snapshot"))
            risky = text_of(await call(c, "browser_click", ref=ref_of(snap, "Proceed")))
            fine = text_of(await call(c, "browser_click", ref=ref_of(snap, "Save")))
            return risky, fine
    try:
        risky, fine = run(go())
    finally:
        server.selfbrowse_session.close()
    assert 'confirm dialog appeared: "Delete everything?"' in risky and "dismissed" in risky and "guardrail" in risky
    assert 'alert dialog appeared: "Saved!"' in fine and "accepted" in fine


def test_parse_args_reads_permissions_and_dialogs():
    cfg = parse_args(["--permissions", "notifications, geolocation", "--dialogs", "dismiss"])
    assert cfg.permissions == ["notifications", "geolocation"] and cfg.dialogs == "dismiss"
