#!/usr/bin/env python3
"""Harvest a PyInstaller dist tree into a WiX v4 ComponentGroup fragment.

A pure-Python replacement for `heat.exe` / `wix harvest`. The WiX v4
toolchain shipped a partially-working harvester that's fiddly across
versions; rolling our own keeps the build pipeline tiny and deterministic.

What it does:
  - Walks the source dir recursively
  - For every file: emits a <Component>/<File> pair under a synthesised
    <Directory> hierarchy rooted at INSTALLFOLDER (DirectoryRef)
  - Stable Component GUIDs derived from the relative path so the same
    file -> same GUID across builds (per-user MSI: GUID stability matters
    for component identity but not for the MSI ProductCode)
  - Excludes filenames whose substring matches any pattern in
    packaging/wix/heat-exclusions.txt

Usage:
    python packaging/wix/harvest.py --source <dir> --out <file.wxs> \\
        [--directory-ref INSTALLFOLDER] [--group-id HarvestedComponents] \\
        [--exclusions packaging/wix/heat-exclusions.txt]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from xml.sax.saxutils import escape

# Namespace used by the wxs fragment we emit; matches Locksmith.wxs.
WIX_NS = "http://wixtoolset.org/schemas/v4/wxs"


def deterministic_guid(seed: str) -> str:
    """Make a stable, well-formatted GUID from an arbitrary seed string.

    Not a UUIDv5 (no namespace UUID dependency) — just SHA-256 truncated
    to 128 bits and formatted as 8-4-4-4-12. Sufficient for WiX Component
    Id uniqueness; component GUIDs do not need to be cryptographically
    bound to anything.
    """
    h = hashlib.sha256(seed.encode("utf-8")).digest()[:16]
    hx = h.hex().upper()
    return f"{hx[0:8]}-{hx[8:12]}-{hx[12:16]}-{hx[16:20]}-{hx[20:32]}"


def safe_id(seed: str, prefix: str = "f") -> str:
    """Build a valid WiX Id (start with letter/underscore, ASCII)."""
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{h}"


def load_exclusions(path: Path) -> list[str]:
    out: list[str] = []
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip leading/trailing '*' — we treat patterns as substring matches.
        out.append(line.strip("*"))
    return out


def is_excluded(rel: Path, exclusions: list[str]) -> bool:
    s = str(rel).replace("\\", "/")
    name = rel.name
    for needle in exclusions:
        if needle and (needle in s or needle in name):
            return True
    return False


def emit(
    source: Path,
    out: Path,
    directory_ref: str,
    group_id: str,
    exclusions: list[str],
) -> int:
    if not source.is_dir():
        print(f"harvest: source not a directory: {source}", file=sys.stderr)
        return 2

    # Walk and collect (relative_dir -> [files])
    files_by_dir: dict[Path, list[Path]] = {}
    files_seen = 0
    files_skipped = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        if is_excluded(rel, exclusions):
            files_skipped += 1
            continue
        files_by_dir.setdefault(rel.parent, []).append(rel)
        files_seen += 1

    # Build a directory tree under INSTALLFOLDER.
    # Map: dir Path -> WiX Id assigned to that Directory element.
    dir_ids: dict[Path, str] = {Path("."): directory_ref}
    for d in sorted({dr for dr in files_by_dir if dr != Path(".")}):
        parts = d.parts
        for i in range(len(parts)):
            sub = Path(*parts[: i + 1])
            if sub not in dir_ids:
                dir_ids[sub] = safe_id(f"dir:{sub}", prefix="d")

    # Compose XML.
    lines: list[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(f'<Wix xmlns="{WIX_NS}">')
    lines.append("  <Fragment>")
    lines.append(f'    <DirectoryRef Id="{directory_ref}">')

    # Open nested <Directory> elements depth-first; close in reverse.
    sorted_dirs = sorted(d for d in dir_ids if d != Path("."))

    def open_dir_chain(rel_dir: Path, depth: int) -> None:
        parts = rel_dir.parts
        for i, name in enumerate(parts):
            sub = Path(*parts[: i + 1])
            sid = dir_ids[sub]
            indent = "      " + "  " * (i + 1)
            lines.append(f'{indent}<Directory Id="{sid}" Name="{escape(name)}">')

    def close_dir_chain(rel_dir: Path) -> None:
        parts = rel_dir.parts
        for i in range(len(parts), 0, -1):
            indent = "      " + "  " * i
            lines.append(f"{indent}</Directory>")

    # Strategy: emit each directory's files inside an opened/closed chain.
    # Inefficient (re-opens shared parents) but produces valid XML and
    # PyInstaller dist trees are shallow enough that the bloat is small.
    # Use a more careful tree-walk: emit hierarchically.
    def walk(prefix: Path, depth: int) -> None:
        # Files directly in prefix
        if prefix in files_by_dir:
            for rel_file in files_by_dir[prefix]:
                src = source / rel_file
                file_id = safe_id(f"file:{rel_file}", prefix="f")
                comp_id = safe_id(f"comp:{rel_file}", prefix="c")
                guid = deterministic_guid(f"locksmith-msi-component:{rel_file}")
                indent = "      " + "  " * depth
                # Per-user MSI components use HKCU registry as KeyPath so
                # MSI is happy without a per-file KeyPath="yes".
                lines.append(
                    f'{indent}<Component Id="{comp_id}" Guid="{guid}">'
                )
                lines.append(
                    f'{indent}  <File Id="{file_id}" Source="{escape(str(src))}" '
                    f'KeyPath="yes" />'
                )
                lines.append(f"{indent}</Component>")
        # Subdirectories
        children = sorted(
            {d for d in dir_ids if d.parent == prefix and d != prefix}
        )
        for child in children:
            indent = "      " + "  " * depth
            sid = dir_ids[child]
            lines.append(f'{indent}<Directory Id="{sid}" Name="{escape(child.name)}">')
            walk(child, depth + 1)
            lines.append(f"{indent}</Directory>")

    walk(Path("."), 1)

    lines.append("    </DirectoryRef>")

    # Emit a flat ComponentGroup that references every component.
    lines.append(f'    <ComponentGroup Id="{group_id}">')
    for rel_dir, rels in sorted(files_by_dir.items()):
        for rel_file in rels:
            comp_id = safe_id(f"comp:{rel_file}", prefix="c")
            lines.append(f'      <ComponentRef Id="{comp_id}" />')
    lines.append("    </ComponentGroup>")

    lines.append("  </Fragment>")
    lines.append("</Wix>")
    lines.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[harvest] wrote {out} files={files_seen} excluded={files_skipped} "
          f"dirs={len(dir_ids)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--directory-ref", default="INSTALLFOLDER")
    ap.add_argument("--group-id", default="HarvestedComponents")
    ap.add_argument("--exclusions", type=Path, default=None)
    args = ap.parse_args()
    exclusions = load_exclusions(args.exclusions) if args.exclusions else []
    return emit(
        source=args.source,
        out=args.out,
        directory_ref=args.directory_ref,
        group_id=args.group_id,
        exclusions=exclusions,
    )


if __name__ == "__main__":
    raise SystemExit(main())
