"""Keystone integration test for the publisher rebuild (Pub Task 5 + Task 6).

Proves the real end-to-end round-trip the OLD publisher tests faked with manual
``db.wigs.put``:

    publisher AID (witnessed over HTTP, toad=1)
        → anchors a release ``ixn`` carrying the release seal
        → its KEL is exported via ``clonePreIter`` (wigs inline)
        → ``locksmith.update.verify.verify_artifact`` ACCEPTS a matching
          artifact against that KEL (toad met + the per-platform sha256 in the
          seal binds the artifact).

Two tests share one in-process witness harness:

* ``test_publisher_kel_cesr_verifies_against_existing_verifier`` drives the
  *library* pipeline (``publish.anchor_release``) directly.
* ``test_cli_roundtrip_verifies`` (Task 6) drives the operator CLI
  (``incept`` → ``anchor`` → ``publish``) through Click's ``CliRunner``, with
  only S3 + the verifier's ``_fetch_url`` faked — the KERI/witness/kli path is
  fully real.

Approach: PRIMARY (a) — kli subprocess against a threaded in-process witness.
The publisher AID's keys are driven by the real ``kli`` binary (a separate
subprocess), so the in-process keripy witness must serve HTTP CONCURRENTLY
while kli runs. We therefore run the witness ``Doist`` loop in a daemon
background thread and run the ``kli`` subprocess commands against
``http://127.0.0.1:<port>``. There is NO network: the verifier's
``verify._fetch_url`` is monkeypatched to return the locally exported
``kel.cesr`` / anchor-event bytes.

Witness bring-up mirrors ``test_confirmdoer_receipts_over_http.py`` on this
branch (``indirecting.setupWitness`` HTTP-only). The publisher keystore is taught
the witness's HTTP endpoint by seeding its ``locs`` record directly
(``_seed_witness_into_keystore``) — NOT by ``kli oobi resolve``, which on the
KERI v2 base exits 0 while persisting nothing. With the endpoint known,
``--receipt-endpoint`` (forced by ``locksmith_publisher.kli``) routes the icp
receipt back, and the anchor's ``Receiptor`` pass collects the ixn receipt; both
land in the publisher KEL as inline wigs.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

# ``locksmith_publisher`` lives under tools/publisher/src and is not installed
# in the main venv; bootstrap it the same way the publisher's own pyproject
# pythonpath does. (``locksmith`` and ``keri`` resolve normally from the venv.)
_PUB_SRC = Path(__file__).resolve().parents[2] / "tools" / "publisher" / "src"
if str(_PUB_SRC) not in sys.path:
    sys.path.insert(0, str(_PUB_SRC))

from hio.base import doing, tyming  # noqa: E402
from keri.app import habbing, indirecting  # noqa: E402
from keri.db import basing  # noqa: E402
from keri.core import Salter  # noqa: E402
from keri import help, Schemes, Roles  # noqa: E402
from keri.core import eventing, parsing, routing  # noqa: E402
from keri.kering import Vrsn_1_0  # noqa: E402

from locksmith.update import verify  # noqa: E402
from locksmith_publisher import cli as cli_mod  # noqa: E402
from locksmith_publisher import kli, publish  # noqa: E402
from locksmith_publisher.appcast import build_appcast  # noqa: E402
from locksmith_publisher.witnesses import WitnessInfo  # noqa: E402

# Point the kli wrappers at the venv binary (per task spec).
kli.KLI = "/Users/seriouscoderone/code/locksmith/.venv/bin/kli"

WIT_ALIAS = "wan"
# 21-char keystore passcode (bran) — kli init requires exactly 21 chars.
PUB_BRAN = "0123456789abcdefghijk"

#: Brand the anchored seal is cut for. The reference brand, which is also what
#: the CLI resolves by default (brand.brand_id() with no LOCKSMITH_BRAND set) and
#: what verify_artifact's embedded_brand defaults to — so the library test and
#: the CLI test below anchor the same brand, and the verifier's brand gate is
#: checked against a matching pair rather than passing by coincidence.
BRAND = "locksmith"


def _free_port() -> int:
    """Grab an ephemeral TCP port, then release it for the witness to bind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _seed_wit_ends(ctrl_db, wit_hab, wit_url):
    """Seed end-role + loc-scheme records into the witness's OWN db so its
    ``/oobi/<pre>/controller`` route serves a resolvable controller OOBI.

    Reproduces ``tests.conftest.DbSeed.seedWitEnds`` inline for the http
    scheme. ``version=Vrsn_1_0`` is load-bearing — without it ``Parser.parse``
    drives ``allParsator`` into an infinite empty-stream yield loop and hangs
    (documented in test_confirmdoer_receipts_over_http.py).
    """
    rtr = routing.Router()
    rvy = routing.Revery(db=ctrl_db, rtr=rtr)
    kvy = eventing.Kevery(db=ctrl_db, lax=False, local=True, rvy=rvy)
    kvy.registerReplyRoutes(router=rtr)
    psr = parsing.Parser(framed=True, kvy=kvy, rvy=rvy, version=Vrsn_1_0)

    msgs = bytearray()
    msgs.extend(wit_hab.makeEndRole(eid=wit_hab.pre, role=Roles.controller,
                                    stamp=help.nowIso8601()))
    msgs.extend(wit_hab.makeLocScheme(url=wit_url, scheme=Schemes.http,
                                      stamp=help.nowIso8601()))
    psr.parse(ims=msgs)


def _json_block(output: str) -> dict:
    """Parse the JSON object out of a publisher CLI run's captured stdout.

    ``anchor_cmd`` itself echoes only ``json.dumps(info)``, but the library it
    calls prints a human progress line first (``publish.anchor_release`` →
    ``print("anchor: n/toad witness receipts …")``), and ``CliRunner`` captures
    both into ``result.output``. So a bare ``json.loads(r.output)`` fails with
    ``Expecting value: line 1 column 1``.

    This mirrors what the real operator flow does with the same output
    (``sed -n '/^{/,/^}/p'`` in the promote script), so the test parses the CLI
    the same way a human does rather than depending on the command being the
    only thing that writes to stdout.
    """
    start, end = output.index("{"), output.rindex("}")
    return json.loads(output[start:end + 1])


def _seed_witness_into_keystore(*, name, base, bran, wit_hab, wit_url):
    """Teach an EXISTING kli keystore the witness's http endpoint, directly.

    Why this exists instead of ``kli oobi resolve``: on the KERI v2 base
    ``kli oobi resolve`` exits 0 but **persists nothing** — the publisher
    keystore ends up with no loc-scheme and no end-role record for the witness
    (verified: ``hab.fetchUrls(eid=wit)`` → ``Mict([])``, ``db.locs`` → ``None``).

    That is silent and total: ``agenting.httpClient(hab, wit)`` then raises
    ``MissingEntryError``, and ``Receiptor.receipt`` **catches and only logs it**
    (`keri/app/agenting.py:96-100`), so receipt collection returns "cleanly"
    having contacted zero witnesses. Every event stays at 0 wigs and
    ``publish._wait_for_receipts`` burns its full timeout — the
    ``only 0/1 witness receipts`` failure.

    So seed the records the same way the witness seeds its own db
    (``_seed_wit_ends``), but into the publisher's keystore. Must be called with
    no kli subprocess running (LMDB single-writer) and before any command that
    needs to reach the witness — i.e. before incept, which collects the icp
    receipt.

    Writes the ``locs`` record directly rather than replaying signed
    ``/loc/scheme`` reply messages through ``Revery``: that path escrowed
    silently here (records never landed), and the record is the only thing the
    receipt path actually consults — ``httpClient`` calls
    ``hab.fetchUrls(eid=wit, scheme=…)``, which reads exactly
    ``db.locs.getTopItemIter(keys=(eid, scheme))`` and needs a non-empty
    ``url``. ``pin`` (not ``put``) so re-seeding is idempotent.
    """
    hby = habbing.Habery(name=name, base=base, bran=bran)
    try:
        hby.db.locs.pin(keys=(wit_hab.pre, Schemes.http),
                        val=basing.LocationRecord(url=wit_url))
    finally:
        hby.close()


def _run_witness_doist(doers, stop_evt, limit):
    """Drive the witness doers in a bounded Doist loop on a background thread.

    Bounded by ``limit`` (hard ceiling) AND ``stop_evt`` (cooperative stop set
    by the test once verification finishes) so the thread can never truly hang.
    """
    doist = doing.Doist(limit=limit, tock=0.03125, doers=doers)
    doist.enter()
    tymer = tyming.Tymer(tymth=doist.tymen(), duration=limit)
    try:
        while not tymer.expired and not stop_evt.is_set():
            doist.recur()
            time.sleep(doist.tock)
    finally:
        doist.exit()


@dataclass
class _Witness:
    """A live in-process witness serving HTTP on ``url`` (AID = ``hab.pre``)."""
    hab: object
    url: str
    port: int

    @property
    def controller_oobi(self) -> str:
        return f"{self.url}oobi/{self.hab.pre}/controller"

    @property
    def witness_oobi(self) -> str:
        # KERI OOBI convention: /oobi/<aid>/<role>; witness role for the pool.
        return f"{self.url.rstrip('/')}/oobi/{self.hab.pre}/witness"


@pytest.fixture
def witness():
    """Stand up a real in-process keripy witness on a free HTTP port.

    Runs the witness ``Doist`` loop on a daemon background thread so it serves
    HTTP CONCURRENTLY while kli subprocesses talk to it. Yields a ``_Witness``
    handle; tears the thread + Hby down on exit. (Per-keystore ``~/.keri``
    cleanup is the responsibility of each test, which owns the ``base``.)
    """
    port = _free_port()
    wit_url = f"http://127.0.0.1:{port}/"
    stop_evt = threading.Event()
    wit_thread = None

    with habbing.openHby(name="witrt",
                         salt=Salter(raw=b"witsaltwitsalt00").qb64) as witHby:
        try:
            witDoers = indirecting.setupWitness(alias=WIT_ALIAS, hby=witHby,
                                                tcpPort=None, httpPort=port)
            witHab = witHby.habByName(WIT_ALIAS)
            _seed_wit_ends(witHby.db, witHab, wit_url)

            wit_thread = threading.Thread(
                target=_run_witness_doist,
                args=(list(witDoers), stop_evt, 60.0),
                daemon=True,
            )
            wit_thread.start()

            # Give the HTTP server a moment to bind before kli connects.
            deadline = time.time() + 5.0
            while time.time() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                pytest.fail(f"witness HTTP server never bound on port {port}")

            yield _Witness(hab=witHab, url=wit_url, port=port)
        finally:
            stop_evt.set()
            if wit_thread is not None:
                wit_thread.join(timeout=10.0)


def _cleanup_keystore(base: str) -> None:
    """Remove the kli keystore dirs under ``~/.keri`` so the run is hermetic."""
    keri_home = Path(os.path.expanduser("~/.keri"))
    for sub in ("ks", "db", "reg", "cf"):
        target = keri_home / sub / base
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        # cf may be a single <base>.json sibling rather than a dir.
        cf_file = keri_home / sub / f"{base}.json"
        if cf_file.exists():
            cf_file.unlink()


@pytest.mark.integration
def test_publisher_kel_cesr_verifies_against_existing_verifier(tmp_path, witness, monkeypatch):
    """Library round-trip: ``publish.anchor_release`` → ``verify_artifact``."""
    # Unique keystore base so the run is isolated and cleanable under ~/.keri.
    base = f"lsp-rt-{uuid.uuid4().hex[:12]}"
    name = "publisher"
    alias = "release"
    port = witness.port
    witHab = witness.hab

    try:
        # Create the publisher keystore (kli init) with a fixed salt for
        # determinism, then resolve the witness controller OOBI so the
        # publisher learns the witness HTTP endpoint.
        init_salt = Salter(raw=b"publishersalt000").qb64
        kli._run([kli.KLI, "init", "--name", name, "--base", base,
                  "--passcode", PUB_BRAN, "--salt", init_salt])
        # Teach the keystore the witness's http endpoint. NOT via
        # `kli oobi resolve` — on the v2 base that exits 0 and persists nothing,
        # which left every event at 0 wigs (see _seed_witness_into_keystore).
        _seed_witness_into_keystore(name=name, base=base, bran=PUB_BRAN,
                                    wit_hab=witHab, wit_url=witness.url)

        # Incept the publisher AID witnessed (toad=1). --receipt-endpoint
        # (forced by kli.kli_incept) routes the icp receipt back as wigs.
        kli.kli_incept(name=name, alias=alias, bran=PUB_BRAN, base=base,
                       wits=[witHab.pre], toad=1)

        # A fake release artifact.
        artifact = tmp_path / "Locksmith-0.2.0.dmg"
        artifact.write_bytes(b"fake-macos-dmg-payload-" + os.urandom(64))

        # Anchor the release ixn and export the KEL. The ixn is created
        # PROGRAMMATICALLY (hab.interact) and receipted via a stock keripy
        # Receiptor — not `kli interact --receipt-endpoint`, which breaks on the
        # v2 base (see publish.py's module docstring and kli.py's note).
        #
        # `brand` is REQUIRED (multi-brand work): it lands in the seal as
        # {"d", "brand", "ver"}, and the verifier rejects an anchor whose seal
        # brand does not match the app's brand. Use the reference brand so the
        # verifier's brand gate is exercised with a matching pair below.
        info = publish.anchor_release(
            name=name, alias=alias, bran=PUB_BRAN, base=base,
            version="0.2.0", brand=BRAND, artifacts=[("macos", artifact)],
            out_dir=str(tmp_path),
        )
        # The seal actually carries the brand we asked for — a brand-mismatched
        # seal is precisely what the multi-brand verifier work had to reject.
        assert info["release_sad"]["brand"] == BRAND
        assert info["release_sad"]["ver"] == "0.2.0"

        # Read the publisher prefix back out of the exported KEL path.
        pub_pre = Path(info["kel_path"]).name.rsplit("-kel.cesr", 1)[0]

        kel_bytes = Path(info["kel_path"]).read_bytes()
        anchor_bytes = Path(info["anchor_event_path"]).read_bytes()

        # Build the appcast the verifier consumes. URLs are arbitrary —
        # _fetch_url is monkeypatched to return local bytes (no network).
        kel_url = "https://releases.example.com/publisher/v1/kel.cesr"
        anchor_url = f"https://releases.example.com/releases/0.2.0/{info['anchor_said']}.cesr"
        artifact_sha = verify._sha256_file(artifact)[0]
        appcast_raw = build_appcast(
            publisher_aid=pub_pre,
            publisher_kel_url=kel_url,
            releases=[dict(
                version="0.2.0",
                anchor_said=info["anchor_said"],
                platform="macos",
                anchor_url=anchor_url,
                artifact_sha256=artifact_sha,
                artifact_url="https://releases.example.com/releases/0.2.0/Locksmith-0.2.0.dmg",
                # Required since the SAID-native seal work: the appcast carries
                # the release SAD so the verifier can re-derive its SAID and
                # match it against the digest seal in the KEL. Use the SAD the
                # anchor actually produced, not a hand-built copy.
                release_sad=info["release_sad"],
            )],
        )

        def _fake_fetch(url: str) -> bytes:
            if url == kel_url:
                return kel_bytes
            if url == anchor_url:
                return anchor_bytes
            raise AssertionError(f"unexpected fetch url: {url}")

        monkeypatch.setattr(verify, "_fetch_url", _fake_fetch)

        # The real round-trip: the EXISTING verifier accepts the artifact.
        # embedded_brand is passed EXPLICITLY (not left to its "locksmith"
        # default) so the seal-brand-vs-app-brand gate is a deliberate part of
        # what this test proves.
        result = verify.verify_artifact(
            artifact_path=artifact,
            appcast_raw=appcast_raw,
            platform="macos",
            embedded_publisher_aid=pub_pre,
            embedded_kel_sn=info["anchor_sn"],
            embedded_kel_said=info["anchor_said"],
            toad=1,
            embedded_brand=BRAND,
        )

        assert result.ok
        assert result.version == "0.2.0"
        assert result.platform == "macos"
        assert result.publisher_aid == pub_pre
        assert result.anchor_said == info["anchor_said"]
        assert result.artifact_sha256 == artifact_sha
        # toad=1 was actually met by a real witness receipt (the crux —
        # this is what the old tests faked with manual db.wigs.put).
        assert result.witness_receipts >= 1
    finally:
        _cleanup_keystore(base)


@pytest.mark.integration
def test_cli_roundtrip_verifies(tmp_path, witness, monkeypatch):
    """Task 6: drive the OPERATOR CLI end-to-end through the real witness.

    Runs ``incept`` → ``anchor`` → ``publish`` via Click's ``CliRunner``
    against the in-process witness; only S3 (no real AWS) and the verifier's
    ``_fetch_url`` (no network) are faked. The publisher AID is minted by the
    real ``kli`` subprocess (CLI ``incept``), the release ``ixn`` is signed +
    witness-receipted for real, and the exported KEL is replayed by the
    UNMODIFIED ``verify.verify_artifact``.
    """
    from click.testing import CliRunner

    base = f"lsp-cli-{uuid.uuid4().hex[:12]}"
    name = "publisher"
    witHab = witness.hab

    # 1. Wire the in-process witness into the CLI's witness pool (toad=1).
    pool = [WitnessInfo(aid=witHab.pre, oobi=witness.witness_oobi)]
    monkeypatch.setattr(cli_mod, "default_witness_pool", lambda: pool)
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", PUB_BRAN)

    runner = CliRunner()
    try:
        # The CLI's `incept` creates the keystore and immediately needs to reach
        # the witness (it collects the icp receipt), so the keystore must already
        # know the witness's HTTP endpoint. We hook `kli_init` to seed that
        # endpoint the moment the keystore exists.
        real_kli_init = kli.kli_init

        # === In-process test witness endpoint hook (not a production gap) ===
        # WHY: `incept` resolves only witness-role OOBIs from the pool, while the
        # in-process test witness (_seed_wit_ends) publishes its loc-scheme under
        # the *controller* end-role — keripy role-filters that out of a
        # witness-role OOBI reply per KERI conventions. So the pool's OOBI alone
        # cannot teach this keystore the URL.
        #
        # It is seeded DIRECTLY rather than by resolving the /controller OOBI,
        # because on the KERI v2 base `kli oobi resolve` exits 0 and persists
        # nothing (see _seed_witness_into_keystore) — which is what left every
        # event at 0 wigs and made both tests in this file fail.
        #
        # PRODUCTION: the real keri.host federation witnesses serve their
        # loc-scheme in the witness-role OOBI reply (empirically confirmed via
        # curl against live federation), so production `incept` reaches them with
        # no hook. This is a test-harness bridge for the in-process witness, not
        # a workaround for a production gap. NOTE it therefore does NOT cover the
        # v2 oobi-resolve defect for real keystores — see
        # backlog/2026-07-28-kli-oobi-resolve-persists-nothing-on-v2.md.
        def _init_then_learn_witness(**kw):
            out = real_kli_init(**kw)
            # Seed the witness's http loc-scheme straight into the freshly
            # created keystore. This used to call `kli oobi resolve`, which on
            # the v2 base exits 0 but persists NOTHING — so incept and the
            # anchor's Receiptor had no endpoint to reach and every event stayed
            # at 0 wigs (see _seed_witness_into_keystore).
            _seed_witness_into_keystore(name=kw["name"], base=kw["base"],
                                        bran=kw["bran"], wit_hab=witHab,
                                        wit_url=witness.url)
            return out

        monkeypatch.setattr(cli_mod.kli, "kli_init", _init_then_learn_witness)

        r = runner.invoke(cli_mod.cli, ["incept", "--name", name,
                                        "--base", base, "--toad", "1"])
        assert r.exit_code == 0, f"incept failed: {r.output}\n{r.exception!r}"

        # 3. anchor a release over a fake artifact via the CLI (--version 0.2.0).
        artifact = tmp_path / "Locksmith-0.2.0.dmg"
        artifact.write_bytes(b"fake-cli-artifact-" + os.urandom(64))
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        r = runner.invoke(cli_mod.cli, [
            "anchor", "--name", name, "--base", base, "--version", "0.2.0",
            "--macos", str(artifact), "--windows", str(artifact),
            "--out-dir", str(out_dir),
        ])
        assert r.exit_code == 0, f"anchor failed: {r.output}\n{r.exception!r}"
        info = _json_block(r.output)
        anchor_said = info["anchor_said"]
        anchor_sn = info["anchor_sn"]

        artifact_sha = verify._sha256_file(artifact)[0]

        # 4. publish via the CLI with S3 faked (capture KEL + anchor + appcast
        #    bytes) and deploy_config faked (test bucket/cdn/kel-url).
        cdn = "https://releases.example.com"
        kel_url = f"{cdn}/publisher/v1/kel.cesr"
        deploy_cfg = {
            "s3_bucket": "releases.example.com",
            "releases_cdn_base": cdn,
            "publisher_kel_url": kel_url,
            # MUST match this harness's single witness. `publish` self-verifies
            # the exported KEL via replay_kel using cfg.get("toad", 3)
            # (cli.py:305), so omitting it asserted the production 3-of-5
            # federation threshold against a one-witness test rig and failed with
            # WitnessThresholdError('event sn=0 has 1 witness receipts, need
            # toad=3') — a fake-config inconsistency, not a real threshold bug.
            "toad": 1,
        }
        monkeypatch.setattr(cli_mod, "load_deploy_config", lambda: deploy_cfg)

        captured: dict = {}

        class _FakeS3:
            def upload_release(self, *, bucket, kel, anchors, appcast, appcast_key):
                captured["bucket"] = bucket
                captured["kel"] = kel
                captured["anchors"] = anchors
                captured["macos_appcast"] = appcast
                captured["appcast_key"] = appcast_key

            def put_object(self, *, bucket, key, data, content_type):
                captured.setdefault("puts", []).append(
                    {"key": key, "data": data, "content_type": content_type})

            def head_object_size(self, *, bucket, key):
                """Size the appcast records as ``artifact_size`` (cli.py:313).

                Returns the REAL artifact's size rather than a dummy: publish
                HEADs the object it just uploaded, and both platforms in this
                test are the same file, so this is the honest value and keeps
                the generated appcast internally consistent.
                """
                captured.setdefault("heads", []).append(key)
                return artifact.stat().st_size

        monkeypatch.setattr(cli_mod.S3, "default", classmethod(lambda cls: _FakeS3()))

        r = runner.invoke(cli_mod.cli, [
            "publish", "--name", name, "--base", base, "--version", "0.2.0",
            "--anchor-said", anchor_said,
            "--macos-sha256", artifact_sha, "--windows-sha256", artifact_sha,
            "--out-dir", str(out_dir),
        ])
        assert r.exit_code == 0, f"publish failed: {r.output}\n{r.exception!r}"

        # The KEL + anchor bytes the CLI uploaded (captured, never sent to AWS).
        kel_bytes = captured["kel"]
        anchor_bytes = captured["anchors"][anchor_said]
        macos_appcast = captured["macos_appcast"]  # bytes
        assert captured["appcast_key"] == "appcast/v1/macos.json"

        # The CLI builds the anchor_url the verifier will fetch from the cdn.
        anchor_url = f"{cdn}/publisher/v1/anchors/{anchor_said}.cesr"

        # 5. Serve the captured KEL + anchor bytes to the verifier (no network).
        def _fake_fetch(url: str) -> bytes:
            if url == kel_url:
                return kel_bytes
            if url == anchor_url:
                return anchor_bytes
            raise AssertionError(f"unexpected fetch url: {url}")

        monkeypatch.setattr(verify, "_fetch_url", _fake_fetch)

        # The publisher AID minted by the CLI's real kli incept (read back from
        # the keystore the CLI created). It is the publisher's own AID — NOT the
        # witness AID — and it must be the prefix of the KEL the CLI uploaded.
        pub_aid = cli_mod._read_publisher_aid(name=name, base=base, bran=PUB_BRAN)
        assert pub_aid != witHab.pre
        assert (out_dir / f"{pub_aid}-kel.cesr").exists()

        # 6a. sn=0 trust-root pinning path: drive gen-anchor and verify at sn=0.
        #
        # gen-anchor writes publisher_anchor.json with embedded_kel_sn=0 and
        # embedded_kel_hash==publisher_aid (the inception SAID IS the AID prefix).
        # We monkeypatch _publisher_anchor_path so it writes to a tmp file, not
        # the real src/locksmith/release/publisher_anchor.json.
        anchor_doc_path = tmp_path / "publisher_anchor.json"
        monkeypatch.setattr(cli_mod, "_publisher_anchor_path", lambda: anchor_doc_path)
        r = runner.invoke(cli_mod.cli, [
            "gen-anchor", "--name", name, "--base", base, "--toad", "1",
        ])
        assert r.exit_code == 0, f"gen-anchor failed: {r.output}\n{r.exception!r}"
        anchor_doc = json.loads(anchor_doc_path.read_text())
        assert anchor_doc["publisher_aid"] == pub_aid
        assert anchor_doc["embedded_kel_sn"] == 0
        assert anchor_doc["embedded_kel_hash"] == pub_aid  # AID == icp SAID

        # Verify at sn=0: embedded_kel_said=pub_aid (the inception SAID).
        # toad is enforced on ALL events from sn=0 up — both the inception
        # and the release ixn must have >= 1 witness receipt. The appcast
        # still selects the release ixn via anchor_said (downgrade-defence
        # path is not triggered here since anchor_sn == kel tip sn).
        result_sn0 = verify.verify_artifact(
            artifact_path=artifact,
            appcast_raw=macos_appcast,
            platform="macos",
            embedded_publisher_aid=anchor_doc["publisher_aid"],
            embedded_kel_sn=0,
            embedded_kel_said=anchor_doc["embedded_kel_hash"],
            toad=1,
        )
        assert result_sn0.ok
        # Proves the inception event also has a real witness receipt.
        assert result_sn0.witness_receipts >= 1

        # 6b. The original ixn-pinned round-trip (sn=anchor_sn) — keep both.
        result = verify.verify_artifact(
            artifact_path=artifact,
            appcast_raw=macos_appcast,
            platform="macos",
            embedded_publisher_aid=pub_aid,
            embedded_kel_sn=anchor_sn,
            embedded_kel_said=anchor_said,
            toad=1,
        )

        assert result.ok
        # toad=1 was met by a REAL witness receipt collected over HTTP for the
        # release ixn the CLI's `anchor` command signed + witnessed.
        assert result.witness_receipts >= 1
    finally:
        _cleanup_keystore(base)
