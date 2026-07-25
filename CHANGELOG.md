# Changelog

User-facing release notes. The section for the running version is bundled into
the app and rendered in the **What's New** dialog after an update
(`locksmith.update.notes` → `ui/window.py:_maybe_show_whats_new`), so write
these for users, not for developers: what changed for them, not which commit.

Format: one `## <version>` heading per release, newest first. The heading text
must be the bare semver (matching `pyproject.toml`) so the runtime lookup finds
it. Bullets under it are rendered as Markdown.

## 0.3.2

- Fixed in-app updates for Usurance: the update verifier checked the wrong
  release feed, so every update was rejected as unverified.
- **What's New** now shows the real release notes for the version you upgraded
  to, and appears for patch updates too (previously only major/minor).

## 0.3.1

- Fixed the Usurance app opening to the vault picker instead of its own
  role-selection home screen — its bundled role surfaces were missing from the
  packaged app.
- The Usurance app icon now sits on a white rounded plate so it reads clearly in
  the dock and taskbar.

## 0.3.0

- Multi-role support: apply for and hold several roles at once, each with its own
  credential-gated surface.
- Rebuilt brand packaging so every build carries a single, self-consistent set of
  brand assets.
- **About** now shows the exact build and the bundled KERI library revision.

## 0.2.21

- Fixed a certificate error that prevented vaults from opening in the packaged
  app.
- The KERI Foundation panel is now included in packaged builds.
