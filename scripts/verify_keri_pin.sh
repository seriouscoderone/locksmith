#!/usr/bin/env bash
# Verify the `keri` pin actually installs and carries the modules we depend on.
#
# WHY THIS EXISTS: the dev venv is editable-installed against the local keripy
# checkout, so `import keri` resolves the WORKING TREE and a green local suite says
# nothing about the pinned commit. This is the only check that reaches the pin.
set -euo pipefail

PIN=$(grep -oE 'keri @ git\+[^"]+' pyproject.toml | head -1)
[ -n "$PIN" ] || { echo "no keri pin found in pyproject.toml"; exit 1; }
echo "pin: $PIN"

PROBE=$(mktemp -d)
trap 'rm -rf "$PROBE"' EXIT
python3.14 -m venv "$PROBE/venv"
"$PROBE/venv/bin/pip" install -q "${PIN#keri @ }" || { echo "PIN DOES NOT INSTALL"; exit 1; }
"$PROBE/venv/bin/python" - <<'PY'
import keri
import keri.app.anchoring          # Plan A
import keri.core.sealing           # Plan A
import keri_serviceaid.egf.attestation   # Plan C1
import keri_serviceaid.egf.issuer_role   # Plan C2b
print("OK: keri", keri.__version__, "and every module the app depends on import from the pin")
PY
