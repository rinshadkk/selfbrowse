"""Use the browser layer on its own, with no model: snapshot, dropdowns, find, tabs, frames.

This is what the model sees and does, so it is a good way to debug a page.

    python examples/12_browser_only.py
"""
from selfbrowse import Browser

with Browser(headless=True) as b:
    b.goto("https://example.com")
    print(b.snapshot().text)            # the numbered list the model reads

    print(b.visible_text()[:200])       # the text on screen (what `read` returns)
    print(b.find_text("domain"))        # scroll to a word and show its context

    snap = b.snapshot()
    link = next(e for e in snap.elements if e["role"] == "link")
    print("clicking", link["text"])
    print(b.click_ref(link["ref"]))

    print(b.snapshot().text.splitlines()[:3])   # a [tabs: ...] line appears when a second tab opens
    # b.select_ref(ref, "France")       # native <select>:   pick an option by its text or value
    # b.switch_tab(1); b.close_tab()    # tabs are numbered from 1
    # b.press("ctrl+a")                 # key names are forgiving: "Down", "Return", "esc" all work
