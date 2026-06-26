"""Append-only verification log per spec §9.6 + [[feedback-testing-automated]].

Format: one line per verification attempt; each line is a sequence of
``key=value`` pairs separated by single spaces. Values containing
whitespace or ``=`` are shell-quoted.

Reserved keys (in canonical emit order): ``ts``, ``outcome``, ``version``,
``publisher_aid``, ``anchor_said``. Free-form context goes into ``fields``.

Per plan deviation #3: this log is **per-install informational**, not
cryptographic. It exists so Phase 5's UI can render "last 5 update
checks" without re-running the verifier. KERI's KEL provides the
cryptographic append-only history.
"""
from __future__ import annotations

import os
import platform as _platform
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from locksmith.update.errors import SchemaError

_RESERVED = ("ts", "outcome", "version", "publisher_aid", "anchor_said")
_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class VerificationLogEntry:
    ts: str
    outcome: str  # "ok" | "hash_mismatch" | "signature" | "witness" | ...
    version: str
    publisher_aid: str
    anchor_said: str
    fields: dict[str, str] = field(default_factory=dict)


def _app_data_base() -> Path:
    """Return the platform-appropriate Locksmith application data directory."""
    sysname = _platform.system()
    if sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Locksmith"
    elif sysname == "Windows":  # pragma: no cover - selected per OS
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Locksmith"
    else:
        return Path.home() / ".local" / "share" / "locksmith"


def default_log_path() -> Path:
    """Return the platform-appropriate verification log path."""
    return _app_data_base() / "verification.log"


def _quote(v: str) -> str:
    """Shell-quote when whitespace or ``=`` is present; else pass through."""
    if any(c.isspace() for c in v) or "=" in v:
        return shlex.quote(v)
    return v


def _format(entry: VerificationLogEntry) -> str:
    parts = [
        f"ts={_quote(entry.ts)}",
        f"outcome={_quote(entry.outcome)}",
        f"version={_quote(entry.version)}",
        f"publisher_aid={_quote(entry.publisher_aid)}",
        f"anchor_said={_quote(entry.anchor_said)}",
    ]
    for k, v in entry.fields.items():
        if k in _RESERVED:
            raise SchemaError(
                f"reserved key in log fields: {k}",
                log_fields={"reserved_key": k},
            )
        if not _KV_RE.match(f"{k}=x"):
            raise SchemaError(
                f"invalid log field key: {k!r}",
                log_fields={"key": k},
            )
        parts.append(f"{k}={_quote(str(v))}")
    return " ".join(parts)


def append_entry(path: Path, entry: VerificationLogEntry) -> None:
    """Atomically append ``entry`` to ``path`` (creates parents)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = _format(entry) + "\n"
    with path.open("a", encoding="utf-8") as fp:
        fp.write(line)


def _parse_line(raw: str) -> VerificationLogEntry:
    tokens = shlex.split(raw.strip())
    kv: dict[str, str] = {}
    for t in tokens:
        m = _KV_RE.match(t)
        if not m:
            raise SchemaError(
                f"malformed log token: {t!r}",
                log_fields={"token": t},
            )
        kv[m.group(1)] = m.group(2)
    missing = [k for k in _RESERVED if k not in kv]
    if missing:
        raise SchemaError(
            f"log line missing reserved keys: {missing}",
            log_fields={"missing": ",".join(missing)},
        )
    extras = {k: v for k, v in kv.items() if k not in _RESERVED}
    return VerificationLogEntry(
        ts=kv["ts"],
        outcome=kv["outcome"],
        version=kv["version"],
        publisher_aid=kv["publisher_aid"],
        anchor_said=kv["anchor_said"],
        fields=extras,
    )


def read_entries(path: Path) -> list[VerificationLogEntry]:
    """Return all entries from ``path`` sorted by ``ts`` (empty if missing)."""
    if not path.exists():
        return []
    entries: list[VerificationLogEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entries.append(_parse_line(line))
    entries.sort(key=lambda e: e.ts)
    return entries


# --- VerificationResult <-> log bridge --------------------------------------
#
# The Release Verification dialog renders a ``VerificationResult``. The gate
# that produces it runs in the PRE-relaunch process; after a successful update
# the app relaunches into the new build whose process never ran a verify. So we
# PERSIST the result here on success and RELOAD it when the dialog opens — that
# is what makes the proof visible after the install completes.

_RESULT_FIELDS = (
    "platform", "artifact_sha256", "artifact_size", "witness_receipts",
    "kel_tip_sn",
)


def record_verification_result(result, *, path: Path | None = None,
                               ts: str | None = None) -> None:
    """Append a ``VerificationResult`` to the verification log."""
    from datetime import datetime, timezone

    p = path or default_log_path()
    stamp = ts or datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry = VerificationLogEntry(
        ts=stamp,
        outcome="ok" if result.ok else "failed",
        version=result.version,
        publisher_aid=result.publisher_aid,
        anchor_said=result.anchor_said,
        fields={
            "platform": result.platform,
            "artifact_sha256": result.artifact_sha256,
            "artifact_size": str(result.artifact_size),
            "witness_receipts": str(result.witness_receipts),
            "kel_tip_sn": str(result.kel_tip_sn),
        },
    )
    append_entry(p, entry)


def load_last_verification_result(path: Path | None = None):
    """Reconstruct the most recent successful ``VerificationResult`` from the
    log (the proof the Release Verification dialog shows), or ``None``."""
    from locksmith.update.verify import VerificationResult

    p = path or default_log_path()
    ok = [e for e in read_entries(p) if e.outcome == "ok"]
    if not ok:
        return None
    e = ok[-1]  # read_entries sorts by ts ascending
    f = e.fields

    def _int(key: str) -> int:
        try:
            return int(f.get(key, "0") or "0")
        except (TypeError, ValueError):
            return 0

    return VerificationResult(
        ok=True,
        version=e.version,
        platform=f.get("platform", ""),
        publisher_aid=e.publisher_aid,
        anchor_said=e.anchor_said,
        artifact_sha256=f.get("artifact_sha256", ""),
        artifact_size=_int("artifact_size"),
        witness_receipts=_int("witness_receipts"),
        kel_tip_sn=_int("kel_tip_sn"),
    )
