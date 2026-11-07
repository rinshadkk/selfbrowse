from selfbrowse.knowledge import SiteKnowledge, normalize_path

URL = "https://shop.example.com/Some-Long-Product-Name/dp/B0ABC123"


def test_normalize_path():
    assert normalize_path(URL) == "/*/dp/*"
    assert normalize_path("https://x.com/") == "/"
    assert normalize_path("https://x.com/cart") == "/cart"


def click(text):
    return {"tool": "click", "role": "button", "text": text}


def test_flow_needs_two_successes_to_replay(tmp_path):
    kb = SiteKnowledge(tmp_path)
    for _ in range(2):
        assert kb.get_steps(URL) == []          # one success is not enough to trust
        kb.record(URL, click("Accept"))
        kb.commit(success=True)
    assert kb.get_steps(URL) == [click("Accept")]


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
    assert kb.get_steps(URL) == []


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
    for _ in range(2):
        kb.record(URL, click("Accept"))
        kb.commit(success=True)
    kb.record_miss(URL)
    kb.record_miss(URL)
    assert kb.get_steps(URL) == []
