"""Stop and review the request before it is sent to the model."""
from __future__ import annotations

import pytest

from selfbrowse import BrowseAgent
from selfbrowse.llm.base import LLMResponse
from selfbrowse.review import Detector, PayloadReview, ReviewLLM, ReviewStopped, terminal_review
from selfbrowse.types import Usage


class Model:
    model = "fake"

    def __init__(self):
        self.sent = []

    def complete(self, *, system, messages, tools, max_tokens=2048):
        self.sent.append(messages)
        return LLMResponse([{"type": "text", "text": "ok"}], "end_turn", Usage(calls=1))


def user(text):
    return {"role": "user", "content": text}


def call(llm, *msgs):
    return llm.complete(system=[{"text": "s"}], messages=list(msgs), tools=[{"name": "done"}])


def wrap(mode, answers, **kw):
    inner, seen = Model(), []

    def on_review(review: PayloadReview):
        seen.append(review)
        return answers.pop(0) if answers else "send"
    return ReviewLLM(inner, mode=mode, on_review=on_review, presidio=False, **kw), inner, seen


def test_when_flagged_does_not_stop_a_clean_request():
    llm, inner, seen = wrap("when_flagged", [])
    call(llm, user("Task: find the price of a stapler"))
    assert not seen and len(inner.sent) == 1


def test_when_flagged_stops_for_each_built_in_kind():
    for text, kind in (("mail jane@example.com now", "email"), ("call (312) 555-0187", "phone"),
                       ("ssn 123-45-6789", "ssn"), ("card 4242 4242 4242 4242", "card")):
        llm, inner, seen = wrap("when_flagged", ["send"])
        call(llm, user(text))
        assert [f.kind for f in seen[0].flags] == [kind], text
        assert len(inner.sent) == 1


def test_your_own_saved_values_are_flagged():
    llm, inner, seen = wrap("when_flagged", ["stop"], secrets={"HOME_CITY": "Springfield"})
    with pytest.raises(ReviewStopped):
        call(llm, user("Ship it to Springfield"))
    assert seen[0].flags[0].kind == "secret" and seen[0].flags[0].label == "HOME_CITY" and not inner.sent


def test_always_stops_every_call_even_when_nothing_is_flagged():
    llm, inner, seen = wrap("always", ["send", "send"])
    call(llm, user("hello"))
    call(llm, user("hello again"))
    assert len(seen) == 2 and seen[0].flags == [] and len(inner.sent) == 2


def test_stop_sends_nothing_and_ends_the_run():
    llm, inner, seen = wrap("always", ["stop"])
    with pytest.raises(ReviewStopped, match="did not approve"):
        call(llm, user("hello"))
    assert inner.sent == []


def test_redact_sends_the_request_with_the_flagged_text_masked():
    llm, inner, seen = wrap("when_flagged", ["redact"])
    msg = user("write to jane@example.com about the order")
    call(llm, msg)
    assert inner.sent[0][0]["content"] == "write to [email] about the order"
    assert msg["content"] == "write to jane@example.com about the order"        # the caller's own message is untouched


def test_redact_reaches_text_inside_tool_results():
    llm, inner, seen = wrap("when_flagged", ["redact"])
    msg = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": [{"type": "text", "text": "Email: jane@example.com"}]}]}
    call(llm, msg)
    assert inner.sent[0][0]["content"][0]["content"][0]["text"] == "Email: [email]"


def test_a_decision_is_remembered_so_one_email_does_not_stop_every_call():
    llm, inner, seen = wrap("when_flagged", ["send", "send"])
    task = user("Task: reply to jane@example.com")
    call(llm, task)
    call(llm, task, user("page text"))
    assert len(seen) == 1 and len(inner.sent) == 2
    call(llm, task, user("also bob@example.com"))                                  # a different value does stop
    assert len(seen) == 2 and [f.text for f in seen[1].flags] == ["bob@example.com"]


def test_a_redact_decision_keeps_masking_the_same_text_later():
    llm, inner, seen = wrap("when_flagged", ["redact"])
    task = user("Task: reply to jane@example.com")
    call(llm, task)
    call(llm, task, user("page"))
    assert len(seen) == 1 and inner.sent[1][0]["content"] == "Task: reply to [email]"


def test_the_models_own_messages_are_not_scanned():
    llm, inner, seen = wrap("when_flagged", [])
    call(llm, user("hi"), {"role": "assistant", "content": "I will email jane@example.com"})
    assert not seen


def test_no_terminal_and_no_callback_means_stop(monkeypatch):
    monkeypatch.setattr("sys.stdin", type("T", (), {"isatty": lambda self: False})())
    assert terminal_review(PayloadReview(1, "always", "", [], [])) == "stop"
    llm = ReviewLLM(Model(), mode="always", presidio=False)
    with pytest.raises(ReviewStopped):
        call(llm, user("hello"))


def test_a_failing_reviewer_does_not_let_the_request_through():
    inner = Model()

    def boom(review):
        raise RuntimeError("ui crashed")
    llm = ReviewLLM(inner, mode="always", on_review=boom, presidio=False)
    with pytest.raises(ReviewStopped, match="review of the request failed"):
        call(llm, user("hello"))
    assert inner.sent == []


@pytest.mark.parametrize("answer,expected", [(True, "send"), ("send", "send"), ("redact", "redact"), (False, "stop"), (None, "stop"), ("maybe", "stop")])
def test_callback_answers(answer, expected):
    from selfbrowse.review import _decision
    assert _decision(answer) == expected


def test_bad_mode_is_refused():
    with pytest.raises(ValueError):
        ReviewLLM(Model(), mode="sometimes")
    with pytest.raises(ValueError):
        BrowseAgent("t", llm=Model(), review_payload="sometimes")


def test_without_presidio_names_are_not_found_but_always_still_stops():
    d = Detector(presidio=False)
    assert d.scan("Jane Doe lives here") == []
    llm, inner, seen = wrap("always", ["stop"])
    with pytest.raises(ReviewStopped):
        call(llm, user("Jane Doe lives here"))


def test_agent_run_stops_cleanly_when_the_request_is_declined():
    class Browser:
        url = "about:blank"
        headless = True

        def start(self): return self
        def snapshot(self):
            class S:
                text, title, elements = "page", "t", []
            return S()
        def visible_text(self, *a, **k): return ""
        def close(self): pass
    inner = Model()
    agent = BrowseAgent("Email jane@example.com", llm=inner, browser=Browser(), review_payload=True,
                        on_review=lambda r: "stop", home="/tmp/sbS_review_home", learn=False)
    result = agent.run()
    assert not result.success and "did not approve" in (result.error or "") and inner.sent == []
