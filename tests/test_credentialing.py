from types import SimpleNamespace

import pytest
from keri import kering
from keri.kering import Vrsn_1_0

from locksmith.core import credentialing


CRED_SAID = "EKfS5jLqaNs3Hy88VZVfu1gxTleRvb1SgLj7ZSVeL9Xv"
REGISTRY_SAID = "EKqVVG868WDESvfk_E75ExOc-OUzPdPaxD8PVsBczDhN"
TEL_SAID = "ED5PTlTaq3CPiUsG6HnmN-nJ-ZDbpEL0MefSORH6-AWi"
SCHEMA_SAID = "EAW8ju7u_onYZBtuPCJQd_CThQBMH7rq94z2LfnbrSik"


class FakeSignalBridge:
    def __init__(self):
        self.events = []

    def emit_doer_event(self, doer_name, event_type, data):
        self.events.append((doer_name, event_type, data))


class FakeSchemaStore:
    def get(self, keys):
        return SimpleNamespace(
            sed={
                "title": "Test Credential",
                "properties": {
                    "a": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "object", "properties": {}},
                        ]
                    }
                },
            }
        )


class FakeHab:
    name = "issuer"
    pre = REGISTRY_SAID
    kever = SimpleNamespace(serder=SimpleNamespace(pvrsn=Vrsn_1_0))

    def interact(self, data, version=None):
        return b"anchoring-event"

    def rotate(self, data, version=None):
        return b"anchoring-event"


class FakeRegistry:
    estOnly = False
    hab = FakeHab()

    def issue(self, said, dt):
        return SimpleNamespace(pre=REGISTRY_SAID, snh="0", sn=0, said=TEL_SAID)


class FakeSchemaRegistry:
    regk = REGISTRY_SAID
    regd = TEL_SAID
    vcp = SimpleNamespace(raw=b"vcp", pre=REGISTRY_SAID, said=TEL_SAID)


class FakeCtel:
    def __init__(self, said=None):
        self.said = said

    def get(self, keys):
        return self.said


class FakeRgy:
    def __init__(self, calls):
        self.calls = calls
        self.reger = SimpleNamespace()
        self.registry = FakeRegistry()

    def registryByName(self, name):
        return self.registry if name == SCHEMA_SAID else None

    def processEscrows(self):
        self.calls.append("rgy.processEscrows")


def _make_issue_doer(monkeypatch, *, complete_after_retry):
    calls = []
    signal_bridge = FakeSignalBridge()
    rgy = FakeRgy(calls)
    hby = SimpleNamespace(db=SimpleNamespace(schema=FakeSchemaStore()))
    app = SimpleNamespace(vault=SimpleNamespace(hby=hby, rgy=rgy))

    class FakeCounselor:
        def __init__(self, hby):
            self.hby = hby

    class FakeRegistrar:
        def __init__(self, hby, rgy, counselor, auth=None):
            self.auth = auth or {}

        def issue(self, creder, iserder, aserder):
            calls.append("registrar.issue")

    class FakePoster:
        def __init__(self, hby):
            self.hby = hby

    class FakeVerifier:
        def __init__(self, hby, reger):
            self.processed = False

        def processEscrows(self):
            calls.append("verifier.processEscrows")
            self.processed = True

    class FakeCredentialer:
        def __init__(self, hby, rgy, registrar, verifier):
            self.verifier = verifier
            self.completed = False

        def create(self, **kwa):
            calls.append("credentialer.create")
            return SimpleNamespace(said=CRED_SAID, attrib={})

        def issue(self, creder, serder):
            calls.append("credentialer.issue")

        def complete(self, said):
            return self.completed

        def processEscrows(self):
            calls.append("credentialer.processEscrows")
            if complete_after_retry and self.verifier.processed:
                self.completed = True

    monkeypatch.setattr(credentialing.grouping, "Counselor", FakeCounselor)
    monkeypatch.setattr(credentialing, "Registrar", FakeRegistrar)
    monkeypatch.setattr(credentialing.forwarding, "Poster", FakePoster)
    monkeypatch.setattr(credentialing.verifying, "Verifier", FakeVerifier)
    monkeypatch.setattr(credentialing.credentialing, "Credentialer", FakeCredentialer)
    monkeypatch.setattr(
        credentialing.eventing,
        "SealEvent",
        lambda i, s, d: SimpleNamespace(i=i, s=s, d=d),
    )
    monkeypatch.setattr(
        credentialing.serdering,
        "SerderKERI",
        lambda raw: SimpleNamespace(raw=raw),
    )
    monkeypatch.setattr(credentialing.signing, "serialize", lambda *args, **kwa: b"acdc")

    doer = credentialing.IssueCredentialDoer(
        app=app,
        schema_said=SCHEMA_SAID,
        recipient_pre=REGISTRY_SAID,
        attributes={"nickname": "alice"},
        signal_bridge=signal_bridge,
    )
    doer.wind = lambda tymth: None
    doer.extend = lambda doers: calls.append("doer.extend")
    doer.remove = lambda doers: calls.append("doer.remove")
    return doer, calls, signal_bridge


def _run_until_done(generator, limit=8):
    for _ in range(limit):
        try:
            next(generator)
        except StopIteration:
            return

    pytest.fail("IssueCredentialDoer did not finish within the bounded retry loop")


def _immediate_generator_return(generator):
    with pytest.raises(StopIteration) as excinfo:
        next(generator)

    return excinfo.value.value


@pytest.mark.parametrize(
    ("ctel_said", "expected_error"),
    [
        (TEL_SAID, None),
        (None, "already exists but is not complete"),
    ],
)
def test_load_schema_existing_registry_requires_committed_inception(ctel_said, expected_error):
    class FakeRgy:
        reger = SimpleNamespace(ctel=FakeCtel(ctel_said))

        def registryByName(self, name):
            return FakeSchemaRegistry()

    doer = credentialing.LoadSchemaDoer.__new__(credentialing.LoadSchemaDoer)
    doer.rgy = FakeRgy()

    generator = doer._create_registry(SCHEMA_SAID, "Schema Title")

    if expected_error:
        with pytest.raises(kering.MissingEntryError, match=expected_error):
            next(generator)
    else:
        assert _immediate_generator_return(generator) == SCHEMA_SAID


def test_create_registry_pins_interact_version_to_hab_pvrsn(monkeypatch):
    """Task 1 fix: LoadSchemaDoer._create_registry's registry-inception anchor
    must inherit the hab's OWN established version (hab.kever.serder.pvrsn)
    rather than keripy's module-level v2 default, or a v1-held hab silently
    anchors a v2-framed ixn onto its v1 KEL -- poisoning fresh-vault
    cross-party presentation. A distinguishable sentinel (not the real
    Vrsn_1_0/Vrsn_2_0 constants) proves the value is actually threaded
    through, not merely coincidentally equal to a hardcoded default.
    """
    sentinel_pvrsn = object()

    class FakeHabWithVersion:
        name = "issuer"
        pre = REGISTRY_SAID
        kever = SimpleNamespace(serder=SimpleNamespace(pvrsn=sentinel_pvrsn))

        def __init__(self):
            self.interact_calls = []

        def interact(self, data, version=None):
            self.interact_calls.append({"data": data, "version": version})
            return b"anchoring-event"

    class FakeCounselorForCreate:
        def __init__(self, hby):
            self.hby = hby

    class FakePosterForCreate:
        def __init__(self, hby):
            self.hby = hby

    class FakeRegistrarForCreate:
        def __init__(self, hby, rgy, counselor, auth=None):
            self.auth = auth or {}

        def incept(self, iserder, anc):
            pass

        def complete(self, pre, sn=0):
            return True

    class FakeMadeRegistry:
        regk = REGISTRY_SAID
        regd = TEL_SAID
        vcp = SimpleNamespace(raw=b"vcp")

    class FakeRgyForCreate:
        def __init__(self):
            self.reger = SimpleNamespace()

        def registryByName(self, name):
            return None

        def makeRegistry(self, name, prefix, **kwa):
            return FakeMadeRegistry()

        def processEscrows(self):
            pass

    hab = FakeHabWithVersion()

    monkeypatch.setattr(credentialing.grouping, "Counselor", FakeCounselorForCreate)
    monkeypatch.setattr(credentialing, "Registrar", FakeRegistrarForCreate)
    monkeypatch.setattr(credentialing.forwarding, "Poster", FakePosterForCreate)
    monkeypatch.setattr(
        credentialing.serdering,
        "SerderKERI",
        lambda raw: SimpleNamespace(raw=raw),
    )

    doer = credentialing.LoadSchemaDoer.__new__(credentialing.LoadSchemaDoer)
    doer.rgy = FakeRgyForCreate()
    doer.hby = SimpleNamespace(habs={"issuer-aid": hab})
    doer.issuer_aid = "issuer-aid"
    doer.auth_codes = None
    doer.extend = lambda doers: None
    doer.remove = lambda doers: None
    doer.tock = 0.0

    generator = doer._create_registry(SCHEMA_SAID, "Schema Title")

    result = _immediate_generator_return(generator)

    assert result == SCHEMA_SAID
    assert len(hab.interact_calls) == 1
    assert hab.interact_calls[0]["version"] is sentinel_pvrsn, (
        "registry-inception anchor must be pinned to the hab's own "
        "established version, not left at the interact() default"
    )


def test_issue_credential_processes_verifier_escrows_before_completion(monkeypatch):
    doer, calls, signal_bridge = _make_issue_doer(monkeypatch, complete_after_retry=True)

    _run_until_done(doer.issue_credential_do(lambda: 0.0))

    assert calls.index("rgy.processEscrows") < calls.index("verifier.processEscrows")
    assert calls.index("verifier.processEscrows") < calls.index("credentialer.processEscrows")
    assert signal_bridge.events[0][1] == "credential_issued"
    assert signal_bridge.events[0][2]["credential_said"] == CRED_SAID


def test_issue_credential_keeps_retrying_while_credentialer_is_pending(monkeypatch):
    doer, calls, signal_bridge = _make_issue_doer(monkeypatch, complete_after_retry=False)
    generator = doer.issue_credential_do(lambda: 0.0)

    for _ in range(4):
        next(generator)

    generator.close()

    assert signal_bridge.events == []
    assert calls.count("rgy.processEscrows") >= 2
    assert calls.count("verifier.processEscrows") >= 2
    assert calls.count("credentialer.processEscrows") >= 2
