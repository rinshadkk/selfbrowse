"""Reversible masking: the model sees <EMAIL_1>, the page receives the real value."""
import pytest

from selfbrowse import BrowseAgent, Browser
from selfbrowse.guardrails import Guards, PresidioRedact, RedactPII, Vault, build_guards
from tests.conftest import ScriptedLLM

REAL = "priya.raman@acme.com"


# ── the vault ──────────────────────────────────────────────────────────────────────

def test_same_value_same_token_and_numbering_per_kind():
    v = Vault()
    assert v.mint("email", "a@x.com", "https://s.com/") == "<EMAIL_1>"
    assert v.mint("email", "b@x.com", "https://s.com/") == "<EMAIL_2>"
    assert v.mint("email", "a@x.com", "https://s.com/p") == "<EMAIL_1>"
    assert v.mint("person", "Ann", "https://s.com/") == "<PERSON_1>"


def test_restore_accepts_sloppy_brackets_and_never_confuses_1_with_10():
    v = Vault()
    for i in range(10):
        v.mint("email", f"u{i}@x.com", "https://s.com/")
    assert v.restore("<EMAIL_1>", "https://s.com/")[0] == "u0@x.com"
    assert v.restore("EMAIL_1", "https://s.com/")[0] == "u0@x.com"
    assert v.restore("[EMAIL_1]", "https://s.com/")[0] == "u0@x.com"
    assert v.restore("<EMAIL_10>", "https://s.com/")[0] == "u9@x.com"
    assert v.restore("hello EMAIL_77", "https://s.com/")[0] == "hello EMAIL_77"        # unknown: left alone


def test_a_value_is_only_restored_on_the_site_it_came_from():
    v = Vault()
    tok = v.mint("email", "a@x.com", "https://shop.example.com/account")
    assert v.restore(tok, "https://www.shop.example.com/pay") == ("a@x.com", [])
    text, refused = v.restore(tok, "https://evil.test/form")
    assert text == tok and refused == ["EMAIL_1"]
    assert v.restore(tok)[0] == "a@x.com"                      # no url: used for the final answer


# ── the guardrails ─────────────────────────────────────────────────────────────────

def test_redact_pii_masks_with_tokens_and_restore_false_masks_for_good():
    assert RedactPII(restore=False).on_page("mail a@x.com", "u") == "mail [email]"
    g = Guards([RedactPII()])
    masked = g.page("mail a@x.com or a@x.com, card 4111 1111 1111 1111", "https://s.com/")
    assert masked == "mail <EMAIL_1> or <EMAIL_1>, card <CARD_1>"
    assert g.restore("<CARD_1>", "https://s.com/")[0] == "4111 1111 1111 1111"
    assert g.note() and not Guards([RedactPII(restore=False)]).note()


def test_two_masking_guardrails_share_one_numbering():
    class Fake:
        def analyze(self, **k):
            from types import SimpleNamespace as R
            return [R(entity_type="PERSON", score=0.9, start=0, end=3)]
    g = Guards([RedactPII(), PresidioRedact(analyzer=Fake())])
    out = g.page("Ann a@x.com", "https://s.com/")
    assert "<PERSON_1>" in out and "<EMAIL_1>" in out
    assert g.restore(out, "https://s.com/")[0] == "Ann a@x.com"


def test_build_guards_restores_by_default_and_no_restore_turns_it_off():
    g = build_guards(redact_pii=True)
    assert g[0].reversible and Guards(g).vault is not None
    g = build_guards(redact_pii=True, restore=False)
    assert not g[0].reversible and Guards(g).vault is None


# ── end to end through the agent ───────────────────────────────────────────────────

def _form_refs(b):
    b.snapshot()
    return {d["text"]: i for i in range(1, 15) if (d := b.describe_ref(i))}


@pytest.mark.browser
def test_model_types_a_placeholder_and_the_page_gets_the_real_value(site, tmp_path):
    with Browser() as b:
        b.goto(site("profile.html"))
        refs = _form_refs(b)
        ref = next(i for t, i in refs.items() if "Newsletter" in t or t == "")  # the first text box
        llm = ScriptedLLM([("read", {}), ("type", {"ref": ref, "text": "<EMAIL_1>"}), ("done", {"answer": "I used <EMAIL_1>", "success": True})])
        agent = BrowseAgent("subscribe the email on file", llm=llm, browser=b, home=tmp_path, learn=False,
                            guardrails=[RedactPII()], restore_answer=True)
        res = agent.run()
        page_value = b.page.input_value("#e")
    shown = repr(llm.seen)
    assert REAL not in shown and "<EMAIL_1>" in shown                      # the model never saw it
    assert "placeholders like <EMAIL_1>" in shown                           # and was told how to use one
    assert page_value == REAL                                               # the page got it
    assert res.output == f"I used {REAL}"                                   # restore_answer is on
    assert "<EMAIL_1>" in str(res.history[1].input)                         # history keeps the token


@pytest.mark.browser
def test_answer_can_be_kept_masked(site, tmp_path):
    with Browser() as b:
        b.goto(site("profile.html"))
        llm = ScriptedLLM([("read", {}), ("done", {"answer": "it is <EMAIL_1>", "success": True})])
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, learn=False,
                          guardrails=[RedactPII()], restore_answer=False).run()
    assert res.output == "it is <EMAIL_1>"


@pytest.mark.browser
def test_a_token_from_another_site_is_refused(site, tmp_path):
    other = site("shop.html").replace("127.0.0.1", "localhost")
    with Browser() as b:
        b.goto(site("profile.html"))
        refs = _form_refs(b)
        ref = next(iter(refs.values()))
        g = RedactPII()
        llm = ScriptedLLM([("read", {}), ("goto", {"url": other}), ("type", {"ref": 1, "text": "<EMAIL_1>"}),
                           ("done", {"answer": "x", "success": False})])
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, learn=False, guardrails=[g]).run()
    typed = next(s for s in res.history if s.tool == "type")
    assert typed.result.startswith("Blocked") and "different site" in typed.result


@pytest.mark.browser
def test_nothing_is_restored_with_restore_false(site, tmp_path):
    with Browser() as b:
        b.goto(site("profile.html"))
        llm = ScriptedLLM([("read", {}), ("done", {"answer": "ok", "success": True})])
        BrowseAgent("t", llm=llm, browser=b, home=tmp_path, learn=False, guardrails=[RedactPII(restore=False)]).run()
    assert "[email]" in repr(llm.seen) and "placeholders like" not in repr(llm.seen)


def test_a_known_value_is_masked_again_wherever_it_shows_up():
    g = Guards([RedactPII()])
    g.page("mail a@example.com", "https://s.com/")
    echoed = g.page('textbox "Email" (value="a@example.com")', "https://s.com/")
    assert "a@example.com" not in echoed and "<EMAIL_1>" in echoed
    # a name no detector found is still covered once the vault holds it
    g.vault.mint("person", "Priya Raman", "https://s.com/")
    assert g.page('value="Priya Raman"', "https://s.com/") == 'value="<PERSON_1>"'


@pytest.mark.browser
def test_answer_is_restored_by_default(site, tmp_path):
    with Browser() as b:
        b.goto(site("profile.html"))
        llm = ScriptedLLM([("read", {}), ("done", {"answer": "it is <EMAIL_1>", "success": True})])
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, learn=False, guardrails=[RedactPII()]).run()
    assert res.output == f"it is {REAL}" and "<EMAIL_1>" in res.history[-1].input.get("answer", "<EMAIL_1>")


def test_cli_no_restore_needs_a_redaction_flag(capsys):
    from selfbrowse.cli import main
    with pytest.raises(SystemExit) as e:
        main(["--no-restore", "do a thing"])
    assert e.value.code == 2 and "--no-restore needs" in capsys.readouterr().err


def test_mcp_restores_on_the_page_but_the_flag_turns_it_off():
    from selfbrowse.mcp_server import parse_args
    assert parse_args(["--redact-pii"]).restore is True
    assert parse_args(["--redact-pii", "--no-restore"]).restore is False


@pytest.mark.browser
def test_mcp_task_answer_is_never_restored(site, tmp_path, monkeypatch):
    from selfbrowse import mcp_server
    from selfbrowse.mcp_server import BrowserSession, ServerConfig
    llm = ScriptedLLM([("read", {}), ("done", {"answer": "it is <EMAIL_1>", "success": True})])
    cfg = ServerConfig(redact_pii=True, home=tmp_path, learn=False)
    cfg.llm = llm
    with Browser() as b:
        b.goto(site("profile.html"))
        out = BrowserSession(cfg, browser=b).run_task("t", 5)
    assert out["answer"] == "it is <EMAIL_1>"
