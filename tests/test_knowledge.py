from selfbrowse.knowledge import SiteKnowledge, normalize_path

URL = "https://shop.example.com/Some-Long-Product-Name/dp/B0ABC123"


def test_normalize_path():
    assert normalize_path(URL) == "/*/dp/*"
    assert normalize_path("https://x.com/") == "/"
    assert normalize_path("https://x.com/cart") == "/cart"


def click(text):
    return {"tool": "click", "role": "button", "text": text}


def test_same_task_repeated_trusts_only_that_task(tmp_path):
    kb = SiteKnowledge(tmp_path)
    for _ in range(2):
        assert kb.get_steps(URL, "task A") == []        # one success is not enough
        kb.record(URL, click("History"))
        kb.commit(success=True, task="task A")
    assert kb.get_steps(URL, "task A") == [click("History")]
    assert kb.get_steps(URL, "task B") == []            # repeating one task is not "generic"


def test_two_different_tasks_make_a_flow_generic(tmp_path):
    kb = SiteKnowledge(tmp_path)
    for task in ("task A", "task B"):
        kb.record(URL, click("Accept"))
        kb.commit(success=True, task=task)
    assert kb.get_steps(URL, "a third task") == [click("Accept")]


def test_risky_clicks_are_never_learned(tmp_path):
    kb = SiteKnowledge(tmp_path)
    for task in ("a", "b"):
        kb.record(URL, click("Accept"))
        kb.record(URL, click("Buy now"))
        kb.commit(success=True, task=task)
    assert kb.get_steps(URL, "c") == []                 # sealed at the risky control


def test_back_undoes_the_detour(tmp_path):
    kb = SiteKnowledge(tmp_path)
    for task in ("a", "b"):
        kb.record(URL, click("Wrong link"))
        kb.undo_last(URL)
        kb.record(URL, click("Right link"))
        kb.commit(success=True, task=task)
    assert kb.get_steps(URL, "c") == [click("Right link")]


def test_expired_flow_ignored(tmp_path, monkeypatch):
    import time
    kb = SiteKnowledge(tmp_path)
    for task in ("a", "b"):
        kb.record(URL, click("Accept"))
        kb.commit(success=True, task=task)
    monkeypatch.setattr(time, "time", lambda: 4e9)
    assert kb.get_steps(URL, "c") == []


def test_failed_run_teaches_nothing(tmp_path):
    kb = SiteKnowledge(tmp_path)
    kb.record(URL, click("Accept"))
    kb.remember(URL, "search is at the top")
    kb.commit(success=False)
    assert kb.domains() == []


def test_typing_seals_page(tmp_path):
    kb = SiteKnowledge(tmp_path)
    kb.record(URL, click("Accept"))
    kb.record(URL, {"tool": "type"})
    kb.record(URL, click("Search"))
    kb.commit(success=True)
    kb.record(URL, {"tool": "type"})
    assert kb.get_steps(URL, "a") == []


def test_memo_dedup_and_cap(tmp_path):
    kb = SiteKnowledge(tmp_path)
    for i in range(20):
        kb.remember(URL, f"fact {i}")
    kb.remember(URL, "fact 19")
    kb.commit(success=True)
    memo = kb.get_memo(URL)
    assert len(memo) == 12 and memo[-1] == "fact 19" and memo.count("fact 19") == 1


def test_misses_drop_flow(tmp_path):
    kb = SiteKnowledge(tmp_path)
    for task in ("a", "b"):
        kb.record(URL, click("Accept"))
        kb.commit(success=True, task=task)
    kb.record_miss(URL)
    kb.record_miss(URL)
    assert kb.get_steps(URL, "a") == []
