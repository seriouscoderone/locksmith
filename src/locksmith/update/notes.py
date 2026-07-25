"""Release notes for the What's New dialog, read from the bundled CHANGELOG.md.

Source of truth is the repo-root ``CHANGELOG.md`` (one ``## <version>`` section
per release). Build scripts bundle it next to the package so a frozen app can
show the real notes for the version the user just upgraded to, instead of the
"see the release notes online" boilerplate it used to render.

Resolution order mirrors ``locksmith.release.deploy.frozen_release_file``:
PyInstaller lays data files down on disk (``sys._MEIPASS``, and inside a macOS
``.app`` under ``Contents/Frameworks`` / ``Contents/Resources``) even when the
package code lives in the embedded PYZ, so look there first when frozen, then
fall back to the source checkout.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG_NAME = "CHANGELOG.md"

#: A ``## <version>`` heading. Captures the version token so we can match it
#: against the running version without depending on trailing text (a date, a
#: codename) the author may add after it.
_HEADING = re.compile(r"^##\s+v?([0-9]+(?:\.[0-9]+)*)", re.MULTILINE)


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass) / "locksmith" / CHANGELOG_NAME)
            paths.append(Path(meipass) / CHANGELOG_NAME)
        contents = Path(sys.executable).resolve().parent.parent
        for sub in ("Frameworks", "Resources"):
            paths.append(contents / sub / "locksmith" / CHANGELOG_NAME)
            paths.append(contents / sub / CHANGELOG_NAME)
    # Source checkout: src/locksmith/update/notes.py -> repo root is parents[3].
    paths.append(Path(__file__).resolve().parents[3] / CHANGELOG_NAME)
    return paths


def changelog_path() -> Path | None:
    """First existing bundled/source CHANGELOG.md, or None."""
    for p in _candidate_paths():
        if p.is_file():
            return p
    return None


def section_for(version: str, *, text: str | None = None) -> str | None:
    """The Markdown body under ``## <version>``, or None when absent.

    ``version`` is matched on its bare semver token, so a heading may carry
    trailing text. Returns the bullets/paragraphs up to the next ``##``
    heading, stripped; None when there is no such section (callers then fall
    back to generic copy rather than showing an empty modal).
    """
    if text is None:
        path = changelog_path()
        if path is None:
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None

    matches = list(_HEADING.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1) != version:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        return body or None
    return None


def notes_for(version: str, previous: str | None = None) -> str:
    """Render-ready Markdown for ``version``: the real notes when the CHANGELOG
    has them, else the generic upgrade line (never empty).

    Body only — NO "What's new in vX" heading. ``WhatsNewDialog`` already
    renders its own headline plus a version line, so returning one here
    printed the title twice.
    """
    body = section_for(version)
    if body:
        return body
    if previous:
        return (f"You've upgraded from v{previous}. "
                "See the release notes on releases.keri.host for details.")
    return "See the release notes on releases.keri.host for details."
