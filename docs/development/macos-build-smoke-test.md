# macOS DMG Smoke-Test Runbook

**Audience:** release engineer verifying a CI-produced `Locksmith-X.Y.Z.dmg` before announcing it.
**Frequency:** every release.
**Environment:** a clean macOS VM (UTM/Parallels snapshot, never the dev machine).

This is the human-execution checklist that complements automated CI checks. CI proves the artifact built, signed, and notarized. This runbook proves the artifact *installs and runs* the way a real user will see it.

---

## Pre-flight (host machine)

- [ ] Download the DMG from `https://releases.keri.host/releases/X.Y.Z/Locksmith-X.Y.Z.dmg`
- [ ] Confirm the file size matches the size CI reported in the workflow run logs
- [ ] Run `stapler validate Locksmith-X.Y.Z.dmg` — must report "The validate action worked!"
- [ ] Run `spctl --assess --type open --context context:primary-signature -v Locksmith-X.Y.Z.dmg` — must report "accepted, source=Notarized Developer ID"

If any of the above fails, **do not announce the release** — open an incident, do not retry the upload.

---

## On the clean macOS VM

- [ ] Restore the clean-snapshot of the VM (no prior Locksmith install)
- [ ] Use Safari (default browser) to download the DMG from `releases.keri.host`
- [ ] Double-click the DMG in Finder. The DMG window opens with the branded background visible
- [ ] Visual inspection: the Locksmith icon sits in the left half, the Applications symlink sits in the right half, the arrow/visual hint between them is visible
- [ ] drag the Locksmith icon onto the Applications shortcut in the DMG window
- [ ] Eject the DMG (the Finder side-bar entry should disappear cleanly)

## First launch on the clean VM

- [ ] Open `/Applications` in Finder, double-click `Locksmith.app`
- [ ] **Expected:** the app launches with no Gatekeeper dialog ("App downloaded from internet — are you sure?"). Notarization should handle this silently.
- [ ] If you see a Gatekeeper prompt: **STOP**. The notarization or stapling step failed. Re-check the CI logs and the `stapler validate` output above.
- [ ] The main Locksmith window appears within 5 seconds of launch
- [ ] No console flash. No "Python.app" or "ProcessName" generic-icon flash in the Dock — the Dock icon shows the Locksmith icon from the moment the process starts
- [ ] Open Activity Monitor → the running process name is `Locksmith` (not `python` or `Python`)
- [ ] In Activity Monitor → Inspect the process → "Bundle Identifier" reads `host.keri.locksmith`

## Functional sanity (no KERI verification yet — that's Phase 4)

- [ ] Create a new vault, set a passcode, complete onboarding to the home screen
- [ ] Close the app (`Cmd+Q`), reopen it. Vault prompts for passcode and unlocks cleanly
- [ ] In `About Locksmith` → version reads exactly `X.Y.Z` (matches the DMG filename)
- [ ] Optionally launch from terminal: `open -a Locksmith` — should open the same way

## Uninstall sanity

- [ ] Quit Locksmith
- [ ] Drag `Locksmith.app` from `/Applications` to the Trash
- [ ] Empty Trash. No background processes left in Activity Monitor under `Locksmith`

---

## Sign-off

Record on the release ticket:
- DMG SHA256 (output of `shasum -a 256 Locksmith-X.Y.Z.dmg`)
- macOS version used for the smoke test (`sw_vers`)
- Date and engineer initials
- Any deviations from this checklist (none expected — escalate if any)

A release is **not announced** until this checklist is fully ticked.
