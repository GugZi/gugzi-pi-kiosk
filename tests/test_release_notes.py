"""Tests for release summaries embedded in MQTT Update state."""
from gugzi_kiosk.release_notes import summarize_release


RELEASE = """## Changelog

# Changelog

## Next release – updater and MQTT reliability

### Fixed
- Corrected Home Assistant update button failing with `systemd status=203/EXEC` because ZIP installation lost executable permissions on `gugzi-kiosk`.
- Start the updater directly with the installed Python interpreter to avoid requiring CLI executable permissions.
- Restore executable permissions for the kiosk CLI and cursor helper after installation and every GitHub update.

### Added
- A Home Assistant diagnostic sensor for the most recent controller update error.

## Previous smart-kiosk feature update
- This is historical and should not be displayed.

## Changes since previous release
- fix: old notes
"""


def test_current_release_summary_is_short_and_not_historical():
    summary = summarize_release(RELEASE)
    assert 0 < len(summary) <= 255
    assert "Fixed:" in summary
    assert "Added:" in summary
    assert "historical" not in summary
    assert "old notes" not in summary


def test_markdown_does_not_leak_formatting():
    assert "`" not in summarize_release(RELEASE)
    assert "Plain link" in summarize_release("### Added\n- [Plain link](https://example.com)\n")
    assert "https://example.com" not in summarize_release("### Added\n- [Plain link](https://example.com)")


def test_empty_and_nonsensical_release_notes():
    assert summarize_release("") == ""
    assert summarize_release(None) == ""
    assert summarize_release("## Changelog\nNo bullet points.") == ""


def test_long_notes_still_fit_home_assistant():
    summary = summarize_release("### Fixed\n- " + ("long words " * 300))
    assert summary
    assert len(summary) <= 255
    assert summary.endswith("…")


def test_controller_publishes_summary_in_update_state():
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] / "gugzi_kiosk/controller.py").read_text()
    assert "self.release_summary=summarize_release(data.get('body',''))" in script
    assert "obj['release_summary']=self.release_summary" in script
