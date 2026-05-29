import pytest

from locksmith_publisher.witnesses import WitnessInfo
from locksmith_publisher.yubikey import FakeYubiKeyDevice


@pytest.fixture
def fake_witness_pool() -> list[WitnessInfo]:
    return [
        WitnessInfo(aid="BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", oobi="https://staging.keri.host/witness/oobi/BAAA"),
        WitnessInfo(aid="BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB", oobi="https://staging.keri.host/witness/oobi/BBBB"),
        WitnessInfo(aid="BCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC", oobi="https://staging.keri.host/witness/oobi/BCCC"),
    ]


@pytest.fixture
def fake_devices() -> list[FakeYubiKeyDevice]:
    return [
        FakeYubiKeyDevice(serial="laptop-yk", slot="9c"),
        FakeYubiKeyDevice(serial="desktop-yk", slot="9c"),
        FakeYubiKeyDevice(serial="airgapped-usb", slot="9c"),
    ]
