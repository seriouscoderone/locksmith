# -*- encoding: utf-8 -*-
"""The manifest is the whole claim, so every byte that goes into it is pinned here.

`attest()` mints a permanent, public ACDC whose only substantive attribute is a
44-character manifest SAID. Nothing downstream re-reads the shards; a consumer
re-derives that one string. So the manifest half of this page has exactly one
job — produce the SAME string the parser's own tool produces over the same bytes
— and every way of getting it wrong is silent: a different key order, a
different separator, an escaped umlaut, a swallowed subdirectory, a hashed
sidecar. Each one still yields a plausible 44-character `E...`, still renders,
still mints. The credential is simply about a different set of bytes than the
one the actuary looked at.

Two claims in `page.py` are load-bearing doctrine and are checked here rather
than trusted:

* `_build_manifest`/`_manifest_said` say "byte-identical to
  `ipd.manifest.build_manifest`/`manifest_said`" — a row about a file in a
  DIFFERENT repo. Made executable: the parser's `src` goes on `sys.path` and
  both implementations run over the same real directory.
* The module docstring says the serialization matches
  `keri.core.sealing.verifySealedBody`'s opaque-blob path — that is the actual
  consumer, so it is called, not paraphrased.

Fixtures here are real directories on disk laid out the way `ipd/pipeline.py`
lays them out (`index.json`, top-level `.jsonl` shards, `mappings/`,
`matrices/`, `risk-value-tables/`), including the legitimately-empty
`parse-report.jsonl` and a non-ASCII table name — because a simplified stand-in
(flat, ASCII, alphabetical) cannot fail for the three reasons this file exists.
"""
import json
import os
import unicodedata
import zipfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from locksmith.plugins.actuary import page as actuary_page
from locksmith.plugins.actuary.page import ActuaryPage

_MANDATE = "EMandate" + "A" * 36

#: A real .xlsm is a zip. Written as one so `_digest` hashes bytes with the
#: structure the thing it commits to actually has, not `b"fake workbook"`.
_SHEET = b'<?xml version="1.0"?><workbook xmlns="x"><sheets/></workbook>'

#: The layout `ipd/pipeline.py` emits: index.json, top-level shards, and the
#: three table kinds under their own directories. `parse-report.jsonl` is
#: written EMPTY on purpose — `ipd.manifest._digest`'s docstring names it as the
#: shard that must digest rather than raise.
#: The product coordinate `ipd/emit.py::write_index` actually writes. The old
#: fixture recorded only `lineOfBusiness`, which was a simplified stand-in for
#: the file the page now READS three of its four attested attributes out of --
#: exactly the fixture shape that has let defects through here before. `action`
#: is capitalised because `api.py::parse` capitalises it into the index.
_PARSE_FILING_DATE = "2027-03-15"
_PARSE_ACTION = "Publish"


def _index_json(mandate: str) -> bytes:
    """`index.json` as the parser emits it, for one mandate coordinate.

    `files` is left empty and that is a DECLARED simplification: the real writer
    accumulates the shard list there, and nothing this page does reads it (the
    manifest walks the directory itself). Every key the page DOES read is real.
    """
    return json.dumps({
        "product": {
            "lineOfBusiness": "auto",
            "jurisdiction": "US-UT",
            "productMandate": mandate,
            "filingDate": _PARSE_FILING_DATE,
            "action": _PARSE_ACTION,
        },
        "files": [],
        "report": "parse-report.jsonl",
    }, separators=(",", ":")).encode()


_SHARDS: tuple[tuple[str, bytes], ...] = (
    ("index.json", _index_json(_MANDATE)),
    ("metadata.jsonl", b'{"record":"metadata","key":"Program","value":"UT Auto"}\n'),
    ("defaults.jsonl", b'{"record":"default","attribute":"Territory","value":"001"}\n'),
    ("coverages.jsonl", b'{"record":"coverage","coverage":"BI"}\n{"record":"coverage","coverage":"PD"}\n'),
    ("derivation-logic.jsonl", b'{"record":"derivation_logic_header","columns":["target","expr"]}\n'),
    ("calculation-order.jsonl", b'{"record":"calc_order","scope":"global","steps":["base","terr"]}\n'),
    ("parse-report.jsonl", b""),                       # legitimately empty
    ("mappings/Terr_Map.jsonl", b'{"record":"mapping","name":"Terr_Map"}\n'),
    ("matrices/Class_Matrix.jsonl", b'{"record":"matrix","name":"Class_Matrix"}\n'),
    ("risk-value-tables/BI_Base.jsonl", b'{"record":"risk_value_table","name":"BI_Base"}\n'),
    # Non-ASCII, and load-bearing: `ensure_ascii=True` would escape this name in
    # the manifest serialization and change the SAID while every other assertion
    # in this file still passed.
    ("risk-value-tables/Prämie_Zöne.jsonl",
     b'{"record":"risk_value_table","name":"Pr\\u00e4mie_Z\\u00f6ne"}\n'),
)

_EXPECTED_NAMES = [
    "calculation-order.jsonl",
    "coverages.jsonl",
    "defaults.jsonl",
    "derivation-logic.jsonl",
    "index.json",
    "mappings/Terr_Map.jsonl",
    "matrices/Class_Matrix.jsonl",
    "metadata.jsonl",
    "parse-report.jsonl",
    "risk-value-tables/BI_Base.jsonl",
    "risk-value-tables/Prämie_Zöne.jsonl",
]


# --- helpers -----------------------------------------------------------------------


def _page(qtbot):
    shell = QWidget()
    qtbot.addWidget(shell)
    shell.resize(1180, 940)
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    page = ActuaryPage(app=None, parent=shell)
    layout.addWidget(page)
    shell.show()
    qtbot.waitExposed(shell)
    return shell, page


def _write_workbook(path: Path, marker: bytes = b"rev-a") -> Path:
    """A real zip, because a .xlsm is one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", _SHEET.decode())
        zf.writestr("xl/workbook.xml", _SHEET.decode())
        zf.writestr("docProps/custom.xml", marker.decode())
    return path


def _write_parse_dir(parse_dir: Path, *, reverse: bool = False,
                     mandate: str = _MANDATE) -> Path:
    """The real shard layout on disk. `reverse` flips CREATION order only.

    `mandate` is the coordinate the parse records in its own `index.json`. The
    default matches the mandate these tests select, because a parse that names a
    DIFFERENT mandate is refused -- see the conflict test.
    """
    parse_dir.mkdir(parents=True, exist_ok=True)
    shards = list(reversed(_SHARDS)) if reverse else list(_SHARDS)
    for rel, body in shards:
        target = parse_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_index_json(mandate) if rel == "index.json" else body)
    return parse_dir


def _write_sidecar(parse_dir: Path, workbook: Path) -> Path:
    sidecar = parse_dir / actuary_page._WORKBOOK_SIDECAR_NAME
    sidecar.write_text(json.dumps({"workbook_path": str(workbook)}))
    return sidecar


def _parse_fixture(tmp_path: Path, name: str = "parse", *, sidecar: bool = True,
                   reverse: bool = False,
                   mandate: str = _MANDATE) -> tuple[Path, Path]:
    parse_dir = _write_parse_dir(tmp_path / name, reverse=reverse,
                                 mandate=mandate)
    workbook = _write_workbook(tmp_path / f"{name}-source.xlsm")
    if sidecar:
        _write_sidecar(parse_dir, workbook)
    return parse_dir, workbook


def _nfc(names):
    """macOS may hand back the umlauts decomposed; the comparison is about the
    characters, not about which normal form the filesystem chose."""
    return [unicodedata.normalize("NFC", n) for n in names]


def _names(manifest: dict) -> list[str]:
    return _nfc([shard["name"] for shard in manifest["shards"]])


def _ipd_manifest():
    """The parser's own implementation, or a LOUD skip naming what is missing.

    The claim under test is about a file in the sibling `ugard` repo. Nothing
    here vendors it, so a checkout without `ugard` cannot run the differential —
    but it must say so rather than pass. `test_the_manifest_said_is_what_the_
    consumers_own_verifier_re_derives` is the backstop that never skips.
    """
    import sys

    root = Path(os.environ.get("UGARD_ROOT", Path.home() / "code" / "ugard"))
    src = root / "insurance-product" / "parser" / "src"
    if not (src / "ipd" / "manifest.py").is_file():
        pytest.skip(
            f"the parser's own manifest.py is not at {src / 'ipd' / 'manifest.py'} — "
            "set UGARD_ROOT to the ugard checkout to run the differential")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    import ipd.manifest as ipd_manifest
    return ipd_manifest


# --- the cross-repo claim ----------------------------------------------------------


def test_the_manifest_and_said_match_the_parsers_own_implementation(tmp_path):
    """The docstring claim "byte-identical to `ipd.manifest.build_manifest` /
    `manifest_said`" is a doctrine row about a file in ANOTHER repo, and rows
    like it drift silently — nothing in either repo's tests compares them.

    Made executable rather than trusted. Both implementations run over the same
    real parse directory (sidecar-free, so the one deliberate divergence is not
    in play — see `test_the_workbook_sidecar_is_never_hashed_into_the_shards`).
    The two cross-serializations at the end isolate the SERIALIZER from the
    BUILDER: if only `_manifest_said` drifted, `mine == theirs` would still hold
    and only those two lines would fail.
    """
    ipd_manifest = _ipd_manifest()
    parse_dir, workbook = _parse_fixture(tmp_path, sidecar=False)

    mine = actuary_page._build_manifest(parse_dir, workbook)
    theirs = ipd_manifest.build_manifest(parse_dir, workbook)

    assert mine == theirs
    assert list(mine) == list(theirs), (
        "same content, different key order — the SAID is over the serialization, "
        "so this alone changes what a consumer re-derives")
    assert [list(s) for s in mine["shards"]] == [list(s) for s in theirs["shards"]]
    assert actuary_page._manifest_said(mine) == ipd_manifest.manifest_said(theirs)
    # Serializer isolated: same input dict through each side's json.dumps.
    assert actuary_page._manifest_said(theirs) == ipd_manifest.manifest_said(mine)
    assert actuary_page._digest(b"a shard") == ipd_manifest._digest(b"a shard")


def test_the_manifest_said_is_what_the_consumers_own_verifier_re_derives(tmp_path):
    """The serialization is a Python-only canonicalization, and the consumer is
    `keri.core.sealing.verifySealedBody`'s opaque-blob path — a dict with no `d`
    is `json.dumps(separators=(",", ":"), ensure_ascii=False)` and Blake3.

    Calling the real verifier, not restating its arguments: `ensure_ascii=True`
    escapes the umlauts in `Prämie_Zöne.jsonl` and the default `", "`/`": "`
    separators pad every field, and either one produces a perfectly plausible
    SAID that no consumer can reproduce. This is the backstop for the
    cross-repo test above, and it never skips.
    """
    from keri.core.sealing import verifySealedBody

    parse_dir, workbook = _parse_fixture(tmp_path)
    manifest = actuary_page._build_manifest(parse_dir, workbook)
    said = actuary_page._manifest_said(manifest)

    assert any(not n.isascii() for n in _names(manifest)), (
        "the fixture lost its non-ASCII shard name, so ensure_ascii is untested")
    assert verifySealedBody({"d": said}, manifest) is True

    # ...and it is a commitment, not a checksum of the shape: one changed
    # character in one shard name and the same seal must refuse it.
    tampered = json.loads(json.dumps(manifest))
    tampered["shards"][0]["name"] = tampered["shards"][0]["name"].upper()
    assert verifySealedBody({"d": said}, tampered) is False


def test_the_manifest_field_order_is_fixed(tmp_path):
    """Python dicts serialize in insertion order and this manifest is never
    sorted, so the order the literal is written in IS part of the SAID. Swapping
    two lines in the returned dict is a refactor that changes every SAID this
    page has ever computed, with no other symptom.
    """
    parse_dir, workbook = _parse_fixture(tmp_path)
    manifest = actuary_page._build_manifest(parse_dir, workbook)

    assert list(manifest) == ["kind", "workbook_digest", "shards"]
    assert manifest["kind"] == "rate_program_manifest"
    assert all(list(shard) == ["name", "digest"] for shard in manifest["shards"])
    assert json.dumps(manifest, separators=(",", ":"), ensure_ascii=False).startswith(
        '{"kind":"rate_program_manifest","workbook_digest":"E')


# --- the digest --------------------------------------------------------------------


def test_a_zero_byte_shard_digests_instead_of_raising(tmp_path):
    """`_digest`'s docstring makes a falsifiable claim about keripy, and the
    whole reason the function exists rather than calling `Diger(ser=raw)`:
    `Diger.__init__`'s ser-fallback is guarded by `if not ser: raise ex`, so a
    genuinely empty `ser` re-raises. The real parser writes `parse-report.jsonl`
    empty on a clean run — the COMMON case — so the obvious implementation
    would make a clean parse the one that cannot be attested.

    Both halves are measured here: that keripy really does refuse, and that this
    page really does not.
    """
    from keri.core.coring import Diger

    with pytest.raises(Exception) as refused:
        Diger(ser=b"")
    assert "EmptyMaterialError" in type(refused.value).__name__, (
        f"keripy no longer refuses an empty ser (raised {refused.value!r}); the "
        "docstring's premise has changed")

    empty = actuary_page._digest(b"")
    assert len(empty) == 44 and empty.startswith("E")
    assert empty != actuary_page._digest(b"\n"), "an empty shard digests as a newline"

    # ...and through the real walk: the fixture's parse-report.jsonl is 0 bytes.
    parse_dir, workbook = _parse_fixture(tmp_path)
    assert (parse_dir / "parse-report.jsonl").stat().st_size == 0
    manifest = actuary_page._build_manifest(parse_dir, workbook)
    report = next(s for s in manifest["shards"] if s["name"] == "parse-report.jsonl")
    assert report["digest"] == empty


def test_the_digest_is_keripys_blake3_default_for_non_empty_bytes(tmp_path):
    """The `Diger._digest(raw=...)` detour exists to survive `b""` — it must not
    also change the answer for everything else. A different `DigDex` code is a
    one-word edit that keeps the 44-character shape, keeps the leading letter
    plausible, and makes every SAID this page ever emitted unverifiable.
    """
    from keri.core.coring import Diger

    for raw in (b"x", _SHEET, b'{"record":"coverage"}\n', "Prämie".encode()):
        assert actuary_page._digest(raw) == Diger(ser=raw).qb64
    assert actuary_page._digest(b"x").startswith("E")   # Blake3_256, not SHA3/SHA2


# --- the walk ----------------------------------------------------------------------


def test_the_shard_list_is_sorted_by_name_not_by_the_order_the_files_were_walked(tmp_path):
    """`rglob` groups by directory, so its order can never equal the sorted
    order here: `metadata.jsonl` is scanned with the top-level files but sorts
    AFTER `mappings/Terr_Map.jsonl`. Both facts are asserted, so this test
    cannot quietly become a tautology on a filesystem that happens to hand back
    sorted entries.

    Two directories with identical content built in opposite creation order must
    also produce the same SAID: the attestation would otherwise depend on which
    order the parser happened to write its shards in.
    """
    forward, workbook = _parse_fixture(tmp_path, "forward", sidecar=False)
    walked = _nfc([p.relative_to(forward).as_posix()
                   for p in forward.rglob("*") if p.is_file()])
    assert walked != _EXPECTED_NAMES, (
        "the walk order already equals the sorted order, so sorting is untested "
        f"by this fixture: {walked}")

    manifest = actuary_page._build_manifest(forward, workbook)
    assert _names(manifest) == _EXPECTED_NAMES

    backward = _write_parse_dir(tmp_path / "backward", reverse=True)
    other = actuary_page._build_manifest(backward, workbook)
    assert actuary_page._manifest_said(other) == actuary_page._manifest_said(manifest)


def test_shards_in_subdirectories_are_committed_to_by_relative_posix_name(tmp_path):
    """A top-level-only scan silently excludes every rate table the parser
    writes — `mappings/`, `matrices/`, `risk-value-tables/` are where the actual
    rates live — and the manifest still builds, still SAIDs, still mints. The
    only tell is the shard COUNT, which nobody reads.

    Names must also be relative and POSIX: an absolute name would embed the
    tmpdir and no two machines could ever agree on a SAID.
    """
    parse_dir, workbook = _parse_fixture(tmp_path, sidecar=False)
    manifest = actuary_page._build_manifest(parse_dir, workbook)
    names = _names(manifest)

    assert names == _EXPECTED_NAMES
    assert len(names) == len(_SHARDS)
    assert "risk-value-tables/BI_Base.jsonl" in names
    assert "risk-value-tables/Prämie_Zöne.jsonl" in names, (
        "a non-ASCII table name was dropped or mangled")
    assert not any(n.startswith("/") or "\\" in n or str(tmp_path) in n for n in names)


def test_the_workbook_sidecar_is_never_hashed_into_the_shards(tmp_path):
    """The sidecar sits INSIDE the parse directory and names an absolute path on
    whoever's machine produced it. Hashing it would make the SAID depend on
    where the .xlsm happened to live — two actuaries attesting the same parse of
    the same workbook from different directories would commit to different
    manifests, and the mismatch would look like tampering.

    Measured as an equality against the same directory before the sidecar
    existed, not merely as an absence from the list.
    """
    parse_dir, workbook = _parse_fixture(tmp_path, sidecar=False)
    without = actuary_page._build_manifest(parse_dir, workbook)

    _write_sidecar(parse_dir, workbook)
    assert (parse_dir / actuary_page._WORKBOOK_SIDECAR_NAME).is_file()
    with_sidecar = actuary_page._build_manifest(parse_dir, workbook)

    assert actuary_page._WORKBOOK_SIDECAR_NAME not in _names(with_sidecar)
    assert with_sidecar == without
    assert actuary_page._manifest_said(with_sidecar) == actuary_page._manifest_said(without)

    # And it is excluded by NAME, wherever in the tree it lands.
    nested = parse_dir / "risk-value-tables" / actuary_page._WORKBOOK_SIDECAR_NAME
    nested.write_text(json.dumps({"workbook_path": str(workbook)}))
    assert actuary_page._build_manifest(parse_dir, workbook) == without


# --- the SAID is a commitment ------------------------------------------------------


def test_flipping_one_byte_in_one_shard_changes_the_said(tmp_path):
    """The point of the whole exercise. A manifest that hashed shard NAMES, or
    sizes, or the index alone, would pass every structural assertion above and
    still let a rate table be edited after the attestation was minted.
    """
    parse_dir, workbook = _parse_fixture(tmp_path, sidecar=False)
    before = actuary_page._manifest_said(actuary_page._build_manifest(parse_dir, workbook))

    table = parse_dir / "risk-value-tables" / "BI_Base.jsonl"
    raw = bytearray(table.read_bytes())
    raw[-2] ^= 0x01                      # one bit, inside the table's own bytes
    table.write_bytes(bytes(raw))

    after = actuary_page._build_manifest(parse_dir, workbook)
    assert actuary_page._manifest_said(after) != before
    assert _names(after) == _EXPECTED_NAMES, "the file set did not change, only its bytes"


def test_replacing_the_workbook_changes_the_said_though_no_shard_moved(tmp_path):
    """`the_manifest_commits_to_the_workbook_itself` is a rule in the corpus,
    not a nicety: the shards are a lossy read of the .xlsm, so a manifest over
    shards alone lets the source workbook be swapped underneath an attestation
    that claims to be about it.
    """
    parse_dir, workbook = _parse_fixture(tmp_path, sidecar=False)
    first = actuary_page._build_manifest(parse_dir, workbook)

    _write_workbook(workbook, marker=b"rev-b")
    second = actuary_page._build_manifest(parse_dir, workbook)

    assert second["shards"] == first["shards"], "no shard changed"
    assert second["workbook_digest"] != first["workbook_digest"]
    assert actuary_page._manifest_said(second) != actuary_page._manifest_said(first)


# --- _resolve_workbook: each documented refusal ------------------------------------


def test_a_parse_directory_with_no_sidecar_does_not_guess_a_workbook(tmp_path, qtbot):
    """There is no defensible guess. `ipd-parse` writes no copy of the .xlsm and
    records its location nowhere (measured — no field in index.json names it),
    so "the only .xlsm next to the parse" is a heuristic that would let the page
    commit to a workbook nobody chose. Refusing is the contract.
    """
    shell, page = _page(qtbot)
    parse_dir, _workbook = _parse_fixture(tmp_path, sidecar=False)

    assert page._resolve_workbook(parse_dir) is None

    # ...including when something with the sidecar's name is there but is not a file.
    (parse_dir / actuary_page._WORKBOOK_SIDECAR_NAME).mkdir()
    assert page._resolve_workbook(parse_dir) is None
    shell.hide()


def test_a_truncated_sidecar_resolves_nothing_rather_than_raising(tmp_path, qtbot):
    """A sidecar is written by hand or by a script that died mid-write. Half a
    JSON object must be a refusal on the page, not a `JSONDecodeError` escaping
    `load_parse` — which would leave the button re-enabled by the `finally` and
    no banner saying anything at all.
    """
    shell, page = _page(qtbot)
    parse_dir, workbook = _parse_fixture(tmp_path, sidecar=False)
    (parse_dir / actuary_page._WORKBOOK_SIDECAR_NAME).write_text(
        '{"workbook_path": "' + str(workbook))

    assert page._resolve_workbook(parse_dir) is None
    shell.hide()


def test_a_sidecar_with_no_workbook_path_resolves_nothing(tmp_path, qtbot):
    """Well-formed JSON of the wrong shape — a sidecar carrying `{"workbook":
    ...}` or the index's own keys. The KeyError is a refusal, not a crash."""
    shell, page = _page(qtbot)
    parse_dir, workbook = _parse_fixture(tmp_path, sidecar=False)
    (parse_dir / actuary_page._WORKBOOK_SIDECAR_NAME).write_text(
        json.dumps({"workbook": str(workbook), "kind": "sidecar"}))

    assert page._resolve_workbook(parse_dir) is None
    shell.hide()


def test_a_sidecar_that_is_not_an_object_or_names_a_null_resolves_nothing(tmp_path, qtbot):
    """The TypeError clause, which has two distinct triggers and is the one an
    `except (OSError, ValueError, KeyError)` would drop: a JSON array (indexing
    it with a string raises) and an explicit null (`Path(None)` raises). Both
    are shapes a generator writing the sidecar can plausibly emit."""
    shell, page = _page(qtbot)
    parse_dir, workbook = _parse_fixture(tmp_path, sidecar=False)
    sidecar = parse_dir / actuary_page._WORKBOOK_SIDECAR_NAME

    sidecar.write_text(json.dumps([str(workbook)]))
    assert page._resolve_workbook(parse_dir) is None

    sidecar.write_text(json.dumps({"workbook_path": None}))
    assert page._resolve_workbook(parse_dir) is None
    shell.hide()


def test_an_unreadable_sidecar_resolves_nothing(tmp_path, qtbot):
    """The OSError clause. `is_file()` says yes and `read_text()` still raises —
    a parse directory copied off a share, or one whose sidecar a teammate wrote
    with a restrictive umask."""
    shell, page = _page(qtbot)
    parse_dir, workbook = _parse_fixture(tmp_path)
    sidecar = parse_dir / actuary_page._WORKBOOK_SIDECAR_NAME
    assert page._resolve_workbook(parse_dir) == workbook, "precondition"

    os.chmod(sidecar, 0o000)
    try:
        try:
            sidecar.read_text()
        except OSError:
            pass
        else:
            pytest.skip("this process can read a 0o000 file; the OSError clause "
                        "cannot be provoked here")
        assert sidecar.is_file(), "the guard above must not be what refuses it"
        assert page._resolve_workbook(parse_dir) is None
    finally:
        os.chmod(sidecar, 0o644)
    shell.hide()


def test_a_sidecar_naming_a_workbook_that_is_gone_resolves_nothing(tmp_path, qtbot):
    """The sidecar records an absolute path on whoever's machine wrote it, so
    "the file named here does not exist" is the ordinary case on any other
    machine — not an exception. Returning the path anyway would push the failure
    into `_build_manifest`'s `read_bytes`, where it becomes "Could not read the
    parse directory or workbook" instead of the sidecar message that names the
    real problem."""
    shell, page = _page(qtbot)
    parse_dir, workbook = _parse_fixture(tmp_path)
    workbook.unlink()

    assert page._resolve_workbook(parse_dir) is None
    shell.hide()


def test_a_sidecar_naming_a_real_workbook_resolves_it(tmp_path, qtbot):
    """The path the whole manifest hangs off. Returned verbatim — the workbook
    lives OUTSIDE the parse directory (that is the entire reason the sidecar
    exists), so any re-rooting under `parse_dir` would break the normal case."""
    shell, page = _page(qtbot)
    parse_dir, workbook = _parse_fixture(tmp_path)
    assert workbook.parent != parse_dir, "the fixture stopped testing the real layout"

    resolved = page._resolve_workbook(parse_dir)
    assert resolved == workbook
    assert resolved.read_bytes() == workbook.read_bytes()
    shell.hide()


# --- _load_parse_inner: through the real page --------------------------------------


def test_a_path_that_is_not_a_directory_is_reported_and_nothing_is_hashed(tmp_path, qtbot):
    """A pasted path with a typo, or the .xlsm pasted where the parse directory
    belongs — both are one keystroke away. The refusal has to NAME the path,
    because the field is a single line and a long path is scrolled out of view
    exactly when it is wrong.
    """
    shell, page = _page(qtbot)
    missing = tmp_path / "no-such-parse"
    page._parse_dir.setText(str(missing))

    page.load_parse()

    assert page._error_banner.isVisible() is True
    assert "Not a directory" in page._error_banner.text()
    assert str(missing) in page._error_banner.text()
    assert page._parse_manifest is None and page._parse_manifest_said is None
    assert page._manifest_said_label.text() == "—"
    assert page._loaded_from.isVisible() is False
    assert page._attest.isEnabled() is False

    # A file is not a directory either.
    workbook = _write_workbook(tmp_path / "book.xlsm")
    page._parse_dir.setText(str(workbook))
    page.load_parse()
    assert "Not a directory" in page._error_banner.text()
    assert page._parse_manifest_said is None
    shell.hide()


def test_a_parse_directory_without_a_sidecar_names_the_file_it_wanted(tmp_path, qtbot):
    """This is the message the actuary meets FIRST on every real parse
    directory, because `ipd-parse` does not write the sidecar — so it has to say
    the filename to create and why the parser did not create it. "Could not
    load" would strand them.

    Also the guard on `_build_manifest(parse_dir, None)`: without the refusal the
    None reaches `workbook.read_bytes()` and the actuary gets an AttributeError
    escaping `load_parse` instead of a banner.
    """
    shell, page = _page(qtbot)
    parse_dir, _workbook = _parse_fixture(tmp_path, sidecar=False)
    page._parse_dir.setText(str(parse_dir))

    page.load_parse()

    text = page._error_banner.text()
    assert page._error_banner.isVisible() is True
    assert actuary_page._WORKBOOK_SIDECAR_NAME in text, "the file to create is unnamed"
    assert "ipd-parse" in text, "does not say why the parser did not write it"
    assert page._parse_manifest_said is None
    assert page._attest.isEnabled() is False
    shell.hide()


def test_a_workbook_that_cannot_be_read_is_a_banner_not_a_traceback(tmp_path, qtbot):
    """`_resolve_workbook` proves the workbook EXISTS; reading it is a separate
    question and a separate failure. The gap is real — a workbook on a
    disconnected share, or one still being written by Excel. Uncaught, the
    OSError escapes `load_parse` past the `finally`, so the button comes back
    enabled with no banner: the actuary clicks Load Parse and nothing at all
    appears to happen.
    """
    shell, page = _page(qtbot)
    parse_dir, workbook = _parse_fixture(tmp_path)
    os.chmod(workbook, 0o000)
    try:
        try:
            workbook.read_bytes()
        except OSError:
            pass
        else:
            pytest.skip("this process can read a 0o000 file; the OSError path "
                        "cannot be provoked here")
        page._parse_dir.setText(str(parse_dir))

        page.load_parse()

        assert page._error_banner.isVisible() is True
        assert "Could not read the parse directory or workbook" in page._error_banner.text()
        assert page._parse_manifest_said is None
        assert page._loaded_from.isVisible() is False
        assert page._loading_parse is False and page._load_parse.isEnabled() is True
    finally:
        os.chmod(workbook, 0o644)
    shell.hide()


def test_loading_a_real_parse_directory_publishes_the_evidence_and_arms_attest(
        tmp_path, qtbot):
    """The success path, end to end through the widget — the state everything
    else on this page reads.

    Every assertion has an independent oracle rather than the page's own
    arithmetic: the shard list against the layout written on disk, the workbook
    digest against keripy's `Diger` directly, the SAID against
    `verifySealedBody` (the consumer). The mandate and version are set BEFORE
    the load, so an armed Attest button proves `_update_attest_enabled` was
    actually reached at the end of `_load_parse_inner` — the read-back cannot be
    opened without it, and the load looks entirely successful either way.
    """
    from keri.core.coring import Diger
    from keri.core.sealing import verifySealedBody

    shell, page = _page(qtbot)
    parse_dir, workbook = _parse_fixture(tmp_path)

    page._show_error("something earlier went wrong")
    page._selected_mandate_said = _MANDATE
    page._version.setText("2027.1")
    page._parse_dir.setText(str(parse_dir))
    assert page._attest.isEnabled() is False, "armed before anything was loaded"

    page.load_parse()

    assert page._error_banner.isVisible() is False, "a stale failure survived a success"
    manifest = page._parse_manifest
    assert manifest is not None
    assert _names(manifest) == _EXPECTED_NAMES
    assert manifest["workbook_digest"] == Diger(ser=workbook.read_bytes()).qb64
    assert manifest["kind"] == "rate_program_manifest"

    said = page._parse_manifest_said
    assert verifySealedBody({"d": said}, manifest) is True, (
        "the SAID on screen is not the one a consumer re-derives from this manifest")

    assert page._manifest_said_label.text() == said
    assert page._workbook_digest_label.text() == manifest["workbook_digest"]
    assert page._loaded_from.isVisible() is True
    assert str(parse_dir) in page._loaded_from.text(), (
        "two digests are evidence something happened, not evidence of WHICH "
        "directory produced them")

    # The two attributes that are READ rather than asked. The raw value is what
    # gets attested; the screen shows the suite's MM/DD/YYYY.
    assert page._parse_filing_date == _PARSE_FILING_DATE
    assert page._parse_action == _PARSE_ACTION
    assert page._filing_date_label.text() == "03/15/2027"
    assert page._action_label.text() == _PARSE_ACTION
    committed = page._attestation_attributes()
    assert committed["filing_date"] == _PARSE_FILING_DATE, (
        "the display format reached the credential")
    assert committed["action"] == _PARSE_ACTION

    assert page._attest.isEnabled() is True
    assert page._attest_blocker.text() == ""
    shell.hide()


def test_the_filing_date_and_retention_are_not_editable_controls(tmp_path, qtbot):
    """They were a date picker defaulting to TODAY and a combo defaulting to
    Publish. Both are facts `ipd-parse` recorded (`--filing-date`, `--action` ->
    `index.json`), and the schema's own tense says so: "recorded AT PARSE TIME",
    "the parse WAS RUN UNDER". Offering them as choices invited the actuary to
    assert something that contradicts the bytes being attested.

    ux-patterns.md:241: "Read-only | Plain text (not a disabled input) ... Never
    render as a greyed-out input."
    """
    from PySide6.QtWidgets import QComboBox, QDateEdit, QLineEdit

    shell, page = _page(qtbot)
    assert not hasattr(page, "_action") and not hasattr(page, "_filing_date"), (
        "the controls are back")
    assert page.findChildren(QComboBox) == [], "a retention combo is on the page"
    assert page.findChildren(QDateEdit) == [], "a filing-date picker is on the page"
    # The ONE thing the actuary types, and the parse path. Nothing else.
    assert len(page.findChildren(QLineEdit)) == 2, (
        "a third text input appeared; only the parse path and the version are typed")
    shell.hide()


def test_a_parse_that_answers_a_different_mandate_is_refused(tmp_path, qtbot):
    """`index.json`'s `productMandate` is the parse's OWN answer to "which
    mandate is this for". Binding a rate program to a mandate its own parse says
    it does not answer is the same class of defect as attesting directory A's
    digests under directory B's path: a permanent, public, wrong artefact with the
    UI behaving exactly as designed.
    """
    other = "EOtherMandate" + "B" * 31
    shell, page = _page(qtbot)
    parse_dir, _wb = _parse_fixture(tmp_path, mandate=other)
    page._selected_mandate_said = _MANDATE
    page._version.setText("2027.1")
    page._parse_dir.setText(str(parse_dir))

    page.load_parse()

    assert page._parse_manifest_said is not None, "the load itself should succeed"
    assert page._mandate_conflict() is True
    assert page._attest.isEnabled() is False
    assert other[:12] in page._attest_blocker.text()
    # The refusal inside `attest()` itself -- reachable from the drawer's confirm
    # signal, so a disabled button is not the guarantee -- needs a vault, and is
    # asserted in test_attest_issuance.py where one exists.
    shell.hide()


def test_a_parse_that_names_no_mandate_is_not_a_conflict(tmp_path, qtbot):
    """Absent is not disagreement. The parser's own model calls `productMandate`
    a coordinate it records and "never parsed or compared", so a parse produced
    before anyone filled it in has nothing to contradict."""
    shell, page = _page(qtbot)
    parse_dir, _wb = _parse_fixture(tmp_path, mandate="")
    page._selected_mandate_said = _MANDATE
    page._version.setText("2027.1")
    page._parse_dir.setText(str(parse_dir))

    page.load_parse()

    assert page._mandate_conflict() is False
    assert page._attest.isEnabled() is True
    shell.hide()


def test_a_parse_directory_with_no_index_is_refused_by_name(tmp_path, qtbot):
    """Three of the four attested attributes come out of `index.json`, so a
    directory without one cannot be attested at all — and the message has to say
    which file is missing, because "could not load" strands the actuary in front
    of a directory that looks fine."""
    shell, page = _page(qtbot)
    parse_dir, _wb = _parse_fixture(tmp_path)
    (parse_dir / "index.json").unlink()
    page._parse_dir.setText(str(parse_dir))

    page.load_parse()

    assert page._parse_manifest_said is None
    text = page._error_banner.text()
    assert "index.json" in text
    assert "ipd-parse" in text, "does not say what kind of directory this must be"
    shell.hide()


@pytest.mark.parametrize("action", ["publish", "Prod", "", "PUBLISH"])
def test_a_retention_value_outside_the_schemas_enum_is_refused(tmp_path, qtbot, action):
    """The enum is `Publish | Sandbox` and `api.py::parse` capitalises into it, so
    a lower-case or foreign value means the index was not written by a parser this
    page understands. Refusing at load is the difference between a banner and an
    issuance failure after the actuary has confirmed an irreversible mint.

    `"publish"` is the sharp case: it is the CLI's own `choices` spelling, one
    `.capitalize()` short of valid, and would sail through a truthiness check.
    """
    shell, page = _page(qtbot)
    parse_dir, _wb = _parse_fixture(tmp_path)
    index = json.loads((parse_dir / "index.json").read_text())
    index["product"]["action"] = action
    (parse_dir / "index.json").write_text(json.dumps(index))
    page._parse_dir.setText(str(parse_dir))

    page.load_parse()

    assert page._parse_manifest_said is None
    assert repr(action) in page._error_banner.text() or "no filing date" in \
        page._error_banner.text()
    assert page._attest.isEnabled() is False
    shell.hide()


def test_an_empty_parse_directory_field_is_refused_not_read_as_the_cwd(
        tmp_path, qtbot, monkeypatch):
    """Was a strict xfail; the source defect is FIXED and this now holds.

    `Path("".strip())` is `Path(".")` and its `.is_dir()` is True, so an empty
    field used to rglob and hash wherever the process happened to be running and
    then report a missing sidecar — a message about the cwd phrased as if it were
    about a parse directory the actuary never named. Worse in the case that
    matters: launch the app FROM a parse directory, which is the natural thing to
    do, and an empty field hashed it and armed the mint over it.
    """
    shell, page = _page(qtbot)
    monkey_cwd = tmp_path / "cwd-parse"
    _write_parse_dir(monkey_cwd)
    monkeypatch.chdir(monkey_cwd)       # restored on teardown; never a bare os.chdir
    page._parse_dir.setText("   ")

    page.load_parse()

    assert page._parse_manifest_said is None
    assert actuary_page._WORKBOOK_SIDECAR_NAME not in page._error_banner.text(), (
        "the empty field was read as the current working directory")
    shell.hide()
