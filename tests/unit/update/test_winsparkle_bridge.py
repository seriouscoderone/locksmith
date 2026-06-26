"""WinSparkle bridge tests — platform-neutral verification gate.

The ctypes ``load_winsparkle_dll`` path + the real ``can_shutdown`` lifecycle
are exercised on the Windows VM (Task 7). Here we pin the gate logic that runs
inside the C callback.

WinSparkle 0.8.3 exposes NOTHING to its callbacks (no staged path, URL, or
version), so the gate's verifier is a no-arg closure that self-fetches the
appcast + self-downloads + verifies (see ``apping._make_update_verifier_windows``).
It returns ``(ok, version)``; the gate turns that into the ``can_shutdown``
int + the failure toast.
"""
import sys


def test_module_imports_on_all_platforms():
    from locksmith.update import winsparkle_bridge  # noqa: F401


def test_gate_returns_true_on_pass():
    from locksmith.update.winsparkle_bridge import WinSparkleVerifierGate
    logs = []
    gate = WinSparkleVerifierGate(
        verifier=lambda: (True, "0.2.10"),
        log_recorder=lambda **kw: logs.append(kw),
        on_failure=lambda v: None,
    )
    assert gate.can_shutdown_and_install() is True
    assert logs and logs[0]["status"] == "verified"
    assert logs[0]["version"] == "0.2.10"


def test_gate_returns_false_on_fail_and_fires_failure():
    from locksmith.update.winsparkle_bridge import WinSparkleVerifierGate
    failures = []
    logs = []
    gate = WinSparkleVerifierGate(
        verifier=lambda: (False, "0.2.10"),
        log_recorder=lambda **kw: logs.append(kw),
        on_failure=lambda v: failures.append(v),
    )
    assert gate.can_shutdown_and_install() is False
    assert failures == ["0.2.10"]
    assert logs and logs[0]["status"] == "failed"


def test_gate_verifier_exception_is_a_safe_block():
    """The can_shutdown callback runs in WinSparkle's C land — it must NEVER
    raise. An unexpected error blocks the install and shows a toast."""
    from locksmith.update.winsparkle_bridge import WinSparkleVerifierGate

    def _boom():
        raise RuntimeError("kel fetch timed out")

    failures = []
    gate = WinSparkleVerifierGate(
        verifier=_boom,
        log_recorder=lambda **kw: None,
        on_failure=lambda v: failures.append(v),
    )
    assert gate.can_shutdown_and_install() is False
    assert failures == ["unknown"]


def test_load_dll_returns_none_off_windows():
    if sys.platform == "win32":
        import pytest
        pytest.skip("native Windows path")
    from locksmith.update.winsparkle_bridge import load_winsparkle_dll
    assert load_winsparkle_dll() is None


def test_winsparkle_init_returns_triple_of_none_off_windows():
    if sys.platform == "win32":
        import pytest
        pytest.skip("native Windows path")
    from locksmith.update.winsparkle_init import init_winsparkle
    dll, gate, callbacks = init_winsparkle(
        verifier=lambda: (True, ""),
        log_recorder=lambda **k: None,
        on_failure=lambda v: None,
    )
    assert dll is None
    assert gate is None
    assert callbacks is None


def test_winsparkle_appcast_url_is_brand_xml(monkeypatch):
    import locksmith.update.winsparkle_init as wi
    from locksmith.core import branding
    branding._reset_cache_for_tests()
    assert wi._appcast_url() == b"https://releases.keri.host/appcast/v1/windows.xml"


def test_winsparkle_app_details_carry_brand_and_running_version():
    """The frozen exe has no VERSIONINFO, so WinSparkle must be told the
    current version explicitly — (company, app, version) from brand+build_info."""
    import locksmith.update.winsparkle_init as wi
    from locksmith.build_info import LOCKSMITH_VERSION
    from locksmith.core import branding
    branding._reset_cache_for_tests()
    company, app_name, version = wi._app_details()
    assert company == "keri.host"
    assert app_name == "Locksmith"
    assert version == LOCKSMITH_VERSION and version  # non-empty current version
