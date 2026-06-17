"""Keystone integration test for the publisher rebuild (Pub Task 5).

Proves the real end-to-end round-trip the OLD publisher tests faked with manual
``db.wigs.put``:

    publisher AID (witnessed over HTTP, toad=1)
        → anchors a release ``ixn`` carrying the release seal
        → its KEL is exported via ``clonePreIter`` (wigs inline)
        → ``locksmith.update.verify.verify_artifact`` ACCEPTS a matching
          artifact against that KEL (toad met + the per-platform sha256 in the
          seal binds the artifact).

Approach: PRIMARY (a) — kli subprocess against a threaded in-process witness.
The publisher AID's keys are driven by the real ``kli`` binary (a separate
subprocess), so the in-process keripy witness must serve HTTP CONCURRENTLY
while kli runs. We therefore run the witness ``Doist`` loop in a daemon
background thread and run the ``kli`` subprocess commands against
``http://127.0.0.1:<port>``. There is NO network: the verifier's
``verify._fetch_url`` is monkeypatched to return the locally exported
``kel.cesr`` / anchor-event bytes.

Witness bring-up mirrors ``test_confirmdoer_receipts_over_http.py`` on this
branch (``indirecting.setupWitness`` HTTP-only). The OOBI-resolve step lets the
publisher keystore learn the witness HTTP endpoint so ``--receipt-endpoint``
(forced by ``locksmith_publisher.kli``) routes inception/ixn receipts back to
the publisher KEL as inline wigs.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import uuid
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
from keri.core import Salter  # noqa: E402
from keri import help, Schemes, Roles  # noqa: E402
from keri.core import eventing, parsing, routing  # noqa: E402
from keri.kering import Vrsn_1_0  # noqa: E402

from locksmith.update import verify  # noqa: E402
from locksmith_publisher import kli, publish  # noqa: E402
from locksmith_publisher.appcast import build_appcast  # noqa: E402

# Point the kli wrappers at the venv binary (per task spec).
kli.KLI = "/Users/seriouscoderone/code/locksmith/.venv/bin/kli"

WIT_ALIAS = "wan"
# 21-char keystore passcode (bran) — kli init requires exactly 21 chars.
PUB_BRAN = "0123456789abcdefghijk"


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


@pytest.mark.integration
def test_publisher_kel_cesr_verifies_against_existing_verifier(tmp_path, monkeypatch):
    port = _free_port()
    wit_url = f"http://127.0.0.1:{port}/"
    # Unique keystore base so the run is isolated and cleanable under ~/.keri.
    base = f"lsp-rt-{uuid.uuid4().hex[:12]}"
    name = "publisher"
    alias = "release"

    stop_evt = threading.Event()
    wit_thread = None
    keri_home = Path(os.path.expanduser("~/.keri"))

    with habbing.openHby(name="witrt",
                         salt=Salter(raw=b"witsaltwitsalt00").qb64) as witHby:
        try:
            # 1. Witness, HTTP only, on a free port. Run its Doist in a daemon
            #    thread so it serves HTTP while the kli subprocesses talk to it.
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

            # 2. Create the publisher keystore (kli init) with a fixed salt for
            #    determinism, then resolve the witness controller OOBI so the
            #    publisher learns the witness HTTP endpoint.
            init_salt = Salter(raw=b"publishersalt000").qb64
            kli._run([kli.KLI, "init", "--name", name, "--base", base,
                      "--passcode", PUB_BRAN, "--salt", init_salt])
            kli._run([kli.KLI, "oobi", "resolve", "--name", name, "--base", base,
                      "--passcode", PUB_BRAN,
                      "--oobi", f"http://127.0.0.1:{port}/oobi/{witHab.pre}/controller"])

            # 3. Incept the publisher AID witnessed (toad=1). --receipt-endpoint
            #    (forced by kli.kli_incept) routes the icp receipt back as wigs.
            kli.kli_incept(name=name, alias=alias, bran=PUB_BRAN, base=base,
                           wits=[witHab.pre], toad=1)

            # 4. A fake release artifact.
            artifact = tmp_path / "Locksmith-0.2.0.dmg"
            artifact.write_bytes(b"fake-macos-dmg-payload-" + os.urandom(64))

            # 5. Anchor the release ixn (sign+witness via kli) and export the KEL.
            info = publish.anchor_release(
                name=name, alias=alias, bran=PUB_BRAN, base=base,
                version="0.2.0", artifacts=[("macos", artifact)],
                out_dir=str(tmp_path),
            )

            # Read the publisher prefix back out of the exported KEL path.
            pub_pre = Path(info["kel_path"]).name.rsplit("-kel.cesr", 1)[0]

            kel_bytes = Path(info["kel_path"]).read_bytes()
            anchor_bytes = Path(info["anchor_event_path"]).read_bytes()

            # 6. Build the appcast the verifier consumes. URLs are arbitrary —
            #    _fetch_url is monkeypatched to return local bytes (no network).
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
                )],
            )

            def _fake_fetch(url: str) -> bytes:
                if url == kel_url:
                    return kel_bytes
                if url == anchor_url:
                    return anchor_bytes
                raise AssertionError(f"unexpected fetch url: {url}")

            monkeypatch.setattr(verify, "_fetch_url", _fake_fetch)

            # 7. The real round-trip: the EXISTING verifier accepts the artifact.
            result = verify.verify_artifact(
                artifact_path=artifact,
                appcast_raw=appcast_raw,
                platform="macos",
                embedded_publisher_aid=pub_pre,
                embedded_kel_sn=info["anchor_sn"],
                embedded_kel_said=info["anchor_said"],
                toad=1,
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
            stop_evt.set()
            if wit_thread is not None:
                wit_thread.join(timeout=10.0)
            # Clean up the kli keystore so the run is hermetic under ~/.keri.
            for sub in ("ks", "db", "reg", "cf"):
                target = keri_home / sub / base
                if target.exists():
                    import shutil
                    shutil.rmtree(target, ignore_errors=True)
                # cf may be a single <base>.json sibling rather than a dir.
                cf_file = keri_home / sub / f"{base}.json"
                if cf_file.exists():
                    cf_file.unlink()
