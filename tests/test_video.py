import pytest

from selfbrowse import Browser


@pytest.mark.browser
def test_a_video_is_recorded_and_listed_after_close(site, tmp_path):
    with Browser(record_video_dir=tmp_path / "vid") as b:
        b.goto(site("profile.html"))
        b.snapshot()
        b.page.wait_for_timeout(600)
    files = b.video_paths()
    assert len(files) == 1 and files[0].suffix == ".webm" and files[0].stat().st_size > 1000
    assert files[0].parent == tmp_path / "vid"


@pytest.mark.browser
def test_no_video_by_default(site, tmp_path):
    with Browser() as b:
        b.goto(site("profile.html"))
    assert b.video_paths() == []
