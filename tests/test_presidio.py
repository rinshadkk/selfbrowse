"""PresidioRedact: the logic with a fake analyzer (always runs) and the real engine (when installed)."""
from types import SimpleNamespace as R

import pytest

from selfbrowse import guardrails as gr
from selfbrowse.guardrails import PresidioRedact, build_guards


class FakeAnalyzer:
    def __init__(self, results):
        self.results, self.calls = results, []

    def analyze(self, *, text, language, entities, score_threshold):
        self.calls.append((language, entities, score_threshold))
        return self.results


def test_masks_with_labels_and_the_best_overlap_wins():
    text = "Hi Priya Raman, mail priya@acme.com now"
    person_over_email = R(entity_type="PERSON", score=0.85, start=16, end=32)     # "mail priya@acme.com" is wrong
    email = R(entity_type="EMAIL_ADDRESS", score=1.0, start=21, end=35)
    name = R(entity_type="PERSON", score=0.9, start=3, end=14)
    g = PresidioRedact(analyzer=FakeAnalyzer([person_over_email, email, name]), restore=False)
    assert g.on_page(text, "u") == "Hi [person], mail [email] now"
    assert g.count == 2


def test_passes_entities_threshold_and_language_to_the_analyzer():
    fake = FakeAnalyzer([])
    g = PresidioRedact(["PERSON", "LOCATION"], threshold=0.7, language="en", analyzer=fake)
    assert g.on_page("hello", "u") == "hello"
    assert fake.calls == [("en", ["PERSON", "LOCATION"], 0.7)]
    assert PresidioRedact(analyzer=fake).entities == list(PresidioRedact.DEFAULT_ENTITIES)
    assert "LOCATION" not in PresidioRedact.DEFAULT_ENTITIES and "DATE_TIME" not in PresidioRedact.DEFAULT_ENTITIES


def test_empty_text_is_not_analyzed():
    fake = FakeAnalyzer([])
    assert PresidioRedact(analyzer=fake).on_page("  ", "u") == "  " and fake.calls == []


def test_build_guards_adds_it_only_when_asked():
    assert not any(isinstance(x, PresidioRedact) for x in build_guards(redact_pii=True))
    g = build_guards(presidio=True, presidio_entities=["PERSON"], presidio_model="en_core_web_lg")
    p = next(x for x in g if isinstance(x, PresidioRedact))
    assert p.entities == ["PERSON"] and p.model == "en_core_web_lg"


def test_missing_install_gives_a_hint(monkeypatch):
    import builtins
    real = builtins.__import__

    def no_presidio(name, *a, **k):
        if name.startswith("presidio_analyzer"):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_presidio)
    with pytest.raises(RuntimeError, match=r"selfbrowse\[presidio\]"):
        PresidioRedact().check_ready()


def _real_or_skip():
    pytest.importorskip("presidio_analyzer")
    spacy = pytest.importorskip("spacy")
    if not spacy.util.is_package("en_core_web_sm"):
        pytest.skip("python -m spacy download en_core_web_sm")


def test_real_presidio_masks_a_name_and_an_email():
    _real_or_skip()
    g = PresidioRedact(restore=False)
    out = g.on_page("Hello Priya Raman, your email is priya.raman@acme.com. Card 4111 1111 1111 1111.", "u")
    assert "Priya" not in out and "acme.com" not in out and "4111" not in out
    assert "[person]" in out and "[email]" in out and "[card]" in out


def test_real_presidio_entity_list_limits_what_is_masked():
    _real_or_skip()
    out = PresidioRedact(["EMAIL_ADDRESS"], restore=False).on_page("Priya Raman: priya.raman@acme.com", "u")
    assert "Priya Raman" in out and "[email]" in out


def test_real_presidio_unknown_model_gives_a_hint():
    _real_or_skip()
    with pytest.raises(RuntimeError, match="spacy download"):
        PresidioRedact(model="en_no_such_model").check_ready()


@pytest.mark.browser
def test_agent_never_shows_the_model_the_name(site, tmp_path):
    _real_or_skip()
    from selfbrowse import BrowseAgent, Browser
    from tests.conftest import ScriptedLLM
    llm = ScriptedLLM([("read", {}), ("done", {"answer": "ok", "success": True})])
    with Browser() as b:
        b.goto(site("person.html"))
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, learn=False, guardrails=[PresidioRedact(restore=False)]).run()
    seen = str(llm.seen[1])
    assert res.success and "Priya" not in seen and "acme.com" not in seen and "[person]" in seen


def test_cli_stops_early_when_the_model_is_missing(capsys):
    _real_or_skip()
    from selfbrowse.cli import main
    assert main(["--redact-presidio", "--presidio-model", "en_no_such_model", "open example.com"]) == 2
    assert "spacy download en_no_such_model" in capsys.readouterr().err


def test_mcp_server_takes_the_flags():
    pytest.importorskip("mcp")
    from selfbrowse.mcp_server import parse_args
    cfg = parse_args(["--redact-presidio", "--presidio-entities", "PERSON,LOCATION", "--presidio-model", "en_core_web_lg"])
    assert (cfg.presidio, cfg.presidio_entities, cfg.presidio_model) == (True, ["PERSON", "LOCATION"], "en_core_web_lg")
    made = [g for g in cfg.guards(with_budget=False) if isinstance(g, PresidioRedact)]
    assert len(made) == 1 and made[0] is [g for g in cfg.guards(with_budget=True) if isinstance(g, PresidioRedact)][0]
