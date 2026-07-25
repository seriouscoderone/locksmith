"""What's New must render the running version's real CHANGELOG section.

Before this, the modal showed hardcoded boilerplate ("You've upgraded from vX.
See the release notes online"), so a user who took an update had no idea what
changed. The notes now come from the repo-root CHANGELOG.md, bundled into the
app by both PyInstaller specs.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from locksmith.update import notes

REPO_ROOT = Path(__file__).resolve().parents[3]

SAMPLE = """# Changelog

## 0.4.0

- Big new thing.
- Another thing.

## 0.3.2

- Fixed the update verifier for Usurance.

## 0.3.1

- Older stuff.
"""


def test_section_for_extracts_only_that_versions_body():
    body = notes.section_for("0.3.2", text=SAMPLE)
    assert body == "- Fixed the update verifier for Usurance."


def test_section_for_stops_at_the_next_heading():
    body = notes.section_for("0.4.0", text=SAMPLE)
    assert "Big new thing" in body and "Another thing" in body
    assert "Usurance" not in body  # did not bleed into the next section


def test_section_for_unknown_version_is_none():
    assert notes.section_for("9.9.9", text=SAMPLE) is None


def test_notes_for_falls_back_to_generic_copy_when_absent(monkeypatch):
    monkeypatch.setattr(notes, "section_for", lambda *a, **k: None)
    out = notes.notes_for("9.9.9", "9.9.8")
    assert "upgraded from v9.9.8" in out  # never renders an empty modal


def test_notes_for_uses_the_changelog_section_when_present(monkeypatch):
    monkeypatch.setattr(notes, "section_for", lambda *a, **k: "- Real note.")
    out = notes.notes_for("1.2.3", "1.2.2")
    assert "- Real note." in out
    assert "releases.keri.host" not in out  # boilerplate suppressed


def test_notes_for_does_not_repeat_the_dialog_headline(monkeypatch):
    """WhatsNewDialog renders its own "What's new in vX" headline plus a version
    line; notes_for must return BODY ONLY or the title prints twice."""
    monkeypatch.setattr(notes, "section_for", lambda *a, **k: "- Real note.")
    assert "What's new in" not in notes.notes_for("1.2.3", "1.2.2")
    monkeypatch.setattr(notes, "section_for", lambda *a, **k: None)
    assert "What's new in" not in notes.notes_for("1.2.3", "1.2.2")


def test_repo_changelog_has_a_section_for_the_current_version():
    """Release gate: every cut version must ship notes users can read."""
    version = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert notes.section_for(version, text=text), (
        f"CHANGELOG.md has no '## {version}' section — add user-facing notes "
        f"for this release before cutting it")


def test_both_specs_bundle_the_changelog():
    for spec in ("Locksmith.macos.spec", "Locksmith.windows.spec"):
        src = (REPO_ROOT / "packaging" / spec).read_text(encoding="utf-8")
        assert 'CHANGELOG.md"), "locksmith"' in src, f"{spec} must bundle CHANGELOG.md"


def test_wrapped_bullet_stays_one_list_item():
    """The CHANGELOG hard-wraps prose. A continuation line must fold into the
    current <li>, not close the list and emit a flush-left <p> (which rendered
    as "• first line" followed by an unindented paragraph)."""
    from locksmith.ui.dialogs.whats_new import render_markdown

    html = render_markdown(
        "- Fixed in-app updates for Usurance: the verifier checked the wrong\n"
        "  release feed, so every update was rejected.\n"
        "- Second bullet.\n"
    )
    assert html.count("<li>") == 2, html
    assert "release feed" in html
    assert "<p>release feed" not in html  # the old broken rendering
    assert "</ul>" in html


def test_real_changelog_bullets_render_as_single_items():
    """End-to-end on the shipped CHANGELOG section for the current version."""
    from locksmith.ui.dialogs.whats_new import render_markdown

    version = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    body = notes.section_for(
        version, text=(REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    html = render_markdown(body)
    # every bullet is an <li>; no stray paragraph from a wrapped line
    assert html.count("<li>") == body.count("\n- ") + 1, html
    assert "<p>" not in html, html
