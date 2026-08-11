---
description: Runbook for publishing an already-built Locksmith release (both brands) via scripts/promote-release.sh
---

# Publishing a release

You are helping the owner publish version **$ARGUMENTS** (if empty, ask which
version, or read `pyproject.toml`).

## The one rule

There is exactly one way to publish, and it is a committed script:

```bash
AWS_PROFILE=personal ./scripts/promote-release.sh <version>
```

**Never write a new promote script.** Between 0.2.21 and 0.3.6 each cut `sed`-ed a
fresh `/tmp/promote-<version>/promote.sh`; the 0.3.1 cut ran the wrong copy,
re-anchored 0.3.0, and added two permanent junk events to the publisher KEL. If the
script is missing something, **fix the script** — that is why it is committed.

## Division of labour

| Step | Who | Needs |
|---|---|---|
| Build both brands, signed + notarized, upload to S3 | **CI** | triggered by creating a GitHub **Release** (not a tag push) |
| Anchor the release seal in the publisher KEL | **the owner** (or their PUBLISHER session) | the **bran** |
| Publish appcasts + KEL to S3 | same run | `AWS_PROFILE=personal` |

You cannot run the publish yourself: env vars do not survive between your tool calls
and you have no interactive stdin for the silent bran prompt. Prepare everything,
verify everything you can, then hand over one command. The owner can run it in-session
by typing `! <command>`.

## Before handing over the command

1. **Confirm CI finished and the artifacts are live.** All four must return 2xx:
   ```bash
   for u in releases/<v>/Locksmith-<v>.dmg releases/<v>/Locksmith-<v>.msi \
            usurance/releases/<v>/Usurance-<v>.dmg usurance/releases/<v>/Usurance-<v>.msi; do
     curl -s -o /dev/null -w "%{http_code} $u\n" -L -r 0-0 "https://releases.keri.host/$u"
   done
   ```
2. **Dry-run it.** This touches nothing and catches most environment problems:
   ```bash
   AWS_PROFILE=personal LOCKSMITH_PROMOTE_DRY_RUN=1 ./scripts/promote-release.sh <v>
   ```
   It verifies preflight, fetches the artifacts, computes digests, and checks each
   brand's baked anchor against that brand's own live feed — then stops before the KEL.
3. **Only then** give the owner the real command, with the bran line:
   ```bash
   read -rs LOCKSMITH_PUBLISHER_BRAN; echo; export LOCKSMITH_PUBLISHER_BRAN
   AWS_PROFILE=personal ./scripts/promote-release.sh <v>
   ```

## Reading the output

Expect, per brand: fetch → digests → baked-anchor OK → anchor (`N/toad` receipts) →
publish → CDN invalidation → `RESULT: ALL VERIFIED`.

| Symptom | What it means |
|---|---|
| `already anchored at sn=N; reusing it` | **correct** — a re-run is idempotent, not a duplicate |
| `anchor: 0/1 receipts` stalling ~120s | the v2 trap: `kli oobi resolve` persists nothing on v2, so witness discovery was never seeded. A config error, NOT the network |
| `StaleAppcastError` | the feed has not caught up. **Benign** — clients simply are not offered the update. Invalidate/wait, do not go hunting an anchor bug |
| any OTHER verify failure | clients would **refuse** an update the feed advertises. Check the artifact's **baked** anchor, never `src/`. This is the v0.2.21 class |
| `NoCredentialsError` | should be impossible now — it is a preflight check. If it appears after `anchor`, the preflight ordering regressed |

## Afterwards

- Confirm all four JSON feeds and both XML feeds report the new version.
- Note the anchor `sn` per brand (they are sequential: brand 1 at N, brand 2 at N+1).
- Offer the owner the download links and suggest testing the **upgrade** path from the
  previous version, not just a fresh install — that is the only thing that exercises
  Sparkle and the in-app KERI gate together.
- Update `MEMORY.md`'s release-state entry with the new version and anchor sns.

## Do not

- Do not build locally and publish that artifact. The seal binds the digest of the
  **CI-built** binary; a local build has a different digest by construction.
- Do not attempt local signing or notarization — see CLAUDE.md, there are no Apple
  credentials on the dev machine by design.
- Do not promote to "latest" as a side effect. That stays a conscious decision.
