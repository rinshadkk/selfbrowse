import pytest

from selfbrowse import BrowseAgent, Browser
from selfbrowse.prompts import OLD_READ, READ_PREFIX

@pytest.mark.browser
def test_read_sees_only_the_screen_but_full_sees_the_whole_page(site):
    with Browser() as b:
        b.goto(site("long_list.html"))
        assert "the last line" not in b.visible_text()
        whole = b.visible_text(12000, whole=True)
        assert "item 0" in whole and "the last line" in whole


@pytest.mark.browser
def test_a_shortened_label_is_replaced_by_the_full_title_and_an_unlabelled_link_gets_its_title(site):
    with Browser() as b:
        b.goto(site("long_list.html"))
        b.find_text("A Very Long")
        listing = str(b.snapshot())
        text = b.visible_text(12000, whole=True)
    assert "A Very Long Book Title Indeed" in text
    assert "A Very Long Book Title Indeed" in listing and "Image Only Title" in listing


def _read(text):
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": [{"type": "text", "text": text}]}]}


def test_only_the_newest_reads_stay_in_the_conversation():
    msgs = [_read(READ_PREFIX + f"page {i}") for i in range(4)] + [_read("opened something")]
    BrowseAgent._trim_old_reads(msgs, keep=2)
    texts = [m["content"][0]["content"][0]["text"] for m in msgs]
    assert texts == [OLD_READ, OLD_READ, READ_PREFIX + "page 2", READ_PREFIX + "page 3", "opened something"]
    BrowseAgent._trim_old_reads(msgs, keep=2)                    # running it again changes nothing
    assert [m["content"][0]["content"][0]["text"] for m in msgs] == texts


@pytest.mark.browser
def test_find_matches_a_phrase_split_by_inline_markup_but_not_across_blocks(site):
    with Browser() as b:
        b.goto(site("split_label.html"))
        assert "found" in b.find_text("First appeared") and "20 February 1991" in b.find_text("First appeared")
        assert "found" in b.find_text("designed by")
        assert "found" in b.find_text("one two three")
        assert "is not on this page" in b.find_text("alpha beta")       # two list items are not one phrase
