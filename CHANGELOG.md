# Changelog

User-facing release notes. The section for the running version is bundled into
the app and rendered in the **What's New** dialog after an update
(`locksmith.update.notes` → `ui/window.py:_maybe_show_whats_new`), so write
these for users, not for developers: what changed for them, not which commit.

Format: one `## <version>` heading per release, newest first. The heading text
must be the bare semver (matching `pyproject.toml`) so the runtime lookup finds
it. Bullets under it are rendered as Markdown.

## 0.4.1

- Fixed the actuary role on Windows: its workspace failed to load at all, while
  showing the role as active. The clock on its "Last checked" line used a time
  format Windows does not accept, and the error stopped the whole page from
  being built.

## 0.4.0

- Usurance roles now have real working surfaces. The **CUO** declares a product
  mandate on a form built from the ecosystem's own schema; the **actuary**
  attests against the mandate it actually observed, asserting version, filing
  date and retention; the **product designer** assembles the product, and
  Assemble stays disabled until the chain behind it is verifiable — with the
  reason shown instead of a dead button.
- Every one of those signing steps now shows a read-back first: exactly what
  you are about to sign, in plain language, before anything is anchored.
- Roles are now requested and granted, rather than assumed. A workspace asks
  for the role it needs, the administrator issues it, and the wallet opens on
  that role instead of always landing on Home.
- Making a vault the default is now a named action you choose, not a checkbox
  hidden in a dialog.
- Peer connections recover when an address changes: a peer that moved is
  re-dialed at its new address, changing your port re-publishes your endpoint,
  and your own peer OOBI can be read (not just copied) from Settings.
- A peer that is merely unreachable is no longer reported as one that refused.
- Installers now wear the right brand. The Usurance MSI no longer shows
  Locksmith's mark on its welcome screen, and the macOS disk-image window no
  longer tells you to drag "Locksmith" to Applications regardless of which app
  you downloaded.
- Diagnostic logs are per-brand, and unreachable advertised addresses are named
  in them rather than failing silently.

## 0.3.6

- Peer connections now advertise a reachable network address instead of assuming
  the local machine, and the address field is prefilled with the one detected on
  your network — so pairing works between two computers, not just on one.
- Each peer connection now has its own identifier, and an incoming first-contact
  request has to be authorized before anything from it is accepted.
- Usurance: the authority endpoint is reachable again, so role requests get
  through.
- Checkboxes, radio buttons and grouped settings are legible on dark system
  themes.

## 0.3.5

- Usurance now opens to its workspace setup on first launch, and returns you
  straight to your workspace after that, instead of a blank screen.
- The roles screen works in installed builds: a governance-framework file was
  missing from the packaged app, so the screen had nothing to load.

## 0.3.3

- The app icon no longer reverts to a faint version once the window finishes
  loading — the dock and taskbar keep the proper icon.
- **What's New** no longer prints its title twice, keeps each note on a single
  bullet, and scrolls when a release has a lot of notes.

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
