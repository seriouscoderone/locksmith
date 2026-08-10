#!/usr/bin/env bash
#
# scripts/promote-release.sh <version> — anchor + publish an already-BUILT
# release, for every brand, off-CI.
#
# This replaces the per-version `/tmp/promote-<version>/promote.sh` that was
# hand-`sed`-ed from the previous cut every time. That pattern put the version
# in a *copy of the script*, which is how the v0.3.1 cut ran
# `/tmp/promote-0.3.0/promote.sh` by mistake and added two junk events to the
# publisher KEL. Here the version is an ARGUMENT and every other value is
# derived: artifact names from the brand manifests, digests from the bytes S3
# actually serves. See
# backlog/2026-07-25-committed-promote-release-script.md.
#
# What it does NOT do, deliberately:
#   * it never touches CI — the publisher keystore and passphrase stay local;
#   * it never promotes to "latest" for you. Verify, then decide.
#
# Usage:
#   read -rs LOCKSMITH_PUBLISHER_BRAN; echo; export LOCKSMITH_PUBLISHER_BRAN
#   ./scripts/promote-release.sh 0.4.0
#
# The bran comes from $LOCKSMITH_PUBLISHER_BRAN, else a silent prompt. It is
# never echoed and never passed on a command line (the publisher reads the env
# var named by --bran-env).
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
    echo "usage: $0 <version>   e.g. $0 0.4.0" >&2
    exit 2
fi

PUB_NAME="${LOCKSMITH_PUBLISHER_NAME:-publisher}"
PUB_BASE="${LOCKSMITH_PUBLISHER_BASE:-publisher}"
PY="${LOCKSMITH_PY:-$REPO_ROOT/.venv/bin/python}"
PUBLISHER="${LOCKSMITH_PUBLISHER_BIN:-$REPO_ROOT/.venv/bin/locksmith-publisher}"
BRANDS=(${LOCKSMITH_BRANDS:-locksmith usurance})

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# ---- 1. Preflight: the checks that actually caught real failures ----------
# Per the backlog's own scope caveat: shell ergonomics did NOT prevent the
# v0.3.x incidents; THESE checks are what catch that class.

say "preflight"

[[ -x "$PUBLISHER" ]] || die "locksmith-publisher not found at $PUBLISHER.
  A plain \`pip install -e .\` does NOT install tools/publisher. Restore it:
    pip install -e tools/publisher --no-deps
    pip install click boto3 fido2 requests
  (--no-deps matters: its unpinned UPSTREAM keri would clobber the pinned fork.)"

# The version must be the one that was actually cut. Three-way assertion so
# this can never anchor a version that does not exist as a build.
PYPROJECT_VERSION="$("$PY" -c '
import tomllib
with open("pyproject.toml","rb") as f: print(tomllib.load(f)["project"]["version"])')"
[[ "$PYPROJECT_VERSION" == "$VERSION" ]] || die \
    "pyproject version is $PYPROJECT_VERSION but you asked to promote $VERSION"

git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null \
    || die "no tag v$VERSION — promote only what was cut and built"

# Signature presence and signature VALIDITY are different questions, and
# conflating them produced a scary "tag is not signed" warning on a tag that was
# correctly signed: this repo signs with SSH (gpg.format=ssh), and `git tag -v`
# cannot verify an SSH signature without gpg.ssh.allowedSignersFile configured.
# So report the two separately and never imply an unsigned tag when one is
# present.
if git cat-file tag "v$VERSION" 2>/dev/null | grep -qE "BEGIN (SSH|PGP) SIGNATURE"; then
    if git tag -v "v$VERSION" >/dev/null 2>&1; then
        echo "  tag       : v$VERSION (signed, signature verified)"
    else
        echo "  tag       : v$VERSION (signed; not verifiable here — configure"
        echo "              gpg.ssh.allowedSignersFile to check it locally)"
    fi
else
    echo "  WARNING: tag v$VERSION carries NO signature"
fi

echo "  publisher : $PUBLISHER"
echo "  keystore  : name=$PUB_NAME base=$PUB_BASE"
echo "  version   : $VERSION (matches pyproject + tag v$VERSION)"
echo "  brands    : ${BRANDS[*]}"

# Bran: env var, else silent prompt. Exported for the publisher to read.
if [[ -z "${LOCKSMITH_PUBLISHER_BRAN:-}" ]]; then
    read -rs -p "  Publisher bran (not echoed): " LOCKSMITH_PUBLISHER_BRAN
    echo
    export LOCKSMITH_PUBLISHER_BRAN
fi
[[ -n "${LOCKSMITH_PUBLISHER_BRAN:-}" ]] || die "no bran supplied"
echo "  bran      : set (${#LOCKSMITH_PUBLISHER_BRAN} chars, never echoed)"

STAGE="$(mktemp -d "${TMPDIR:-/tmp%/}/promote-$VERSION.XXXXXX" | sed 's#//*#/#g')"
echo "  stage     : $STAGE"

# ---- 2. Per brand: fetch from S3, verify, anchor, publish, verify ---------

CDN="$("$PY" - <<'PY'
import json, pathlib
for p in ("src/locksmith/release/deploy_config.json",
          "src/locksmith/release/deploy_config.example.json"):
    f = pathlib.Path(p)
    if f.is_file():
        print(json.loads(f.read_text())["releases_cdn_base"]); break
else:
    raise SystemExit("no deploy_config.json to read releases_cdn_base from")
PY
)"
echo "  cdn       : $CDN"

for BRAND in "${BRANDS[@]}"; do
    say "brand: $BRAND"

    # "$PY", never a bare `python`: this runs in the operator's own shell (the
    # one holding the bran), which has no venv activated and on macOS may have
    # no `python` on PATH at all.
    PREFIX="$(cd packaging && LOCKSMITH_BRAND="$BRAND" "$PY" -m brandlib id artifact_prefix)"
    RELPATH="$(cd packaging && LOCKSMITH_BRAND="$BRAND" "$PY" -m brandlib id release_prefix)"
    DMG="$STAGE/${PREFIX}-${VERSION}.dmg"
    MSI="$STAGE/${PREFIX}-${VERSION}.msi"

    # Download the bytes S3 actually SERVES — never trust whatever is staged
    # locally. This is what closes the "did I verify the bytes I am anchoring?"
    # gap: the digests below are computed from these downloads.
    for pair in "$DMG:dmg" "$MSI:msi"; do
        dest="${pair%:*}"; ext="${pair##*:}"
        url="$CDN/$RELPATH/$VERSION/${PREFIX}-${VERSION}.${ext}"
        echo "  fetching $url"
        curl -fsSL --retry 3 -o "$dest" "$url" \
            || die "could not fetch $url — did CI finish uploading $BRAND?"
    done

    DMG_SHA="$(shasum -a 256 "$DMG" | cut -d' ' -f1)"
    MSI_SHA="$(shasum -a 256 "$MSI" | cut -d' ' -f1)"
    echo "  dmg sha256: $DMG_SHA"
    echo "  msi sha256: $MSI_SHA"

    # Pre-publish gate (ENFORCED): does the AID baked into this artifact match
    # the AID that signs the brand's live feed? A stale CI anchor secret is
    # invisible from the local source anchor and blocked Sparkle for the whole
    # of v0.2.21. This is deliberately NARROWER than
    # verify-release-artifact.py — it compares publisher AIDs only, so it works
    # BEFORE the feed carries $VERSION. Catching this after publishing would
    # mean the bad feed is already live.
    echo "  pre-publish: baked anchor vs live feed publisher_aid"
    "$PY" scripts/check-baked-anchor.py --dmg "$DMG" --brand "$BRAND" \
        || die "$BRAND: the anchor baked into the artifact does NOT match the AID
  signing the live feed. Every client from this build would bake a trust root
  that cannot verify the feed — Sparkle finds the update, the KERI gate refuses
  it. This is the v0.2.21 failure. Fix the CI LOCKSMITH_PUBLISHER_ANCHOR secret
  and rebuild; do NOT publish."

    if [[ "${LOCKSMITH_PROMOTE_DRY_RUN:-0}" == "1" ]]; then
        echo "  DRY RUN: stopping before anchor. Everything above is verified:"
        echo "    artifacts fetched from the CDN, digests computed, baked anchor"
        echo "    matches this brand's live feed. Nothing has touched the KEL."
        continue
    fi

    say "$BRAND: anchor $VERSION"
    ANCHOR_OUT="$STAGE/anchor-$BRAND"
    mkdir -p "$ANCHOR_OUT"
    LOCKSMITH_BRAND="$BRAND" "$PUBLISHER" anchor \
        --name "$PUB_NAME" --base "$PUB_BASE" \
        --version "$VERSION" \
        --macos "$DMG" --windows "$MSI" \
        --out-dir "$ANCHOR_OUT" | tee "$STAGE/anchor-$BRAND.log"

    # The publisher prints a progress line before the JSON, so take the object.
    ANCHOR_SAID="$("$PY" - "$STAGE/anchor-$BRAND.log" <<'PY'
import json, sys
t = open(sys.argv[1]).read()
d = json.loads(t[t.index("{"):t.rindex("}") + 1])
print(d.get("anchor_said") or d["release_sad"]["d"])
PY
)"
    [[ -n "$ANCHOR_SAID" ]] || die "$BRAND: could not read anchor_said from the anchor output"
    echo "  anchor said: $ANCHOR_SAID"

    say "$BRAND: publish $VERSION"
    LOCKSMITH_BRAND="$BRAND" "$PUBLISHER" publish \
        --name "$PUB_NAME" --base "$PUB_BASE" \
        --version "$VERSION" \
        --anchor-said "$ANCHOR_SAID" \
        --macos-sha256 "$DMG_SHA" --windows-sha256 "$MSI_SHA" \
        --out-dir "$ANCHOR_OUT"

    say "$BRAND: post-publish verification (ENFORCED)"
    "$PY" scripts/verify-release-artifact.py --dmg "$DMG" --msi "$MSI" \
        || die "$BRAND: published $VERSION does NOT verify against the live feed.
  The feed is now advertising an update clients will REFUSE. Investigate before
  promoting to latest — check the artifact's BAKED anchor, not src/."
    echo "  $BRAND: verified against the live feed"
done

say "done"
if [[ "${LOCKSMITH_PROMOTE_DRY_RUN:-0}" == "1" ]]; then
    cat <<EOF
DRY RUN complete for $VERSION — NOTHING WAS PUBLISHED.

Verified for every brand: the artifacts exist on the CDN and were fetched, their
digests were computed from those bytes, and the anchor baked into each build
matches the AID signing that brand's own feed.

Re-run without LOCKSMITH_PROMOTE_DRY_RUN to anchor and publish.
Staged artifacts: $STAGE
EOF
else
    cat <<EOF
Both brands anchored, published and verified for $VERSION.

Promote-to-latest is deliberately NOT automated — it stays a conscious decision.
Staged artifacts and anchor logs: $STAGE
EOF
fi
