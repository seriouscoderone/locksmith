"""WinSparkle bridge tests — platform-neutral verification gate.

The ctypes ``load_winsparkle_dll`` path is exercised by the Windows
integration test in a later task. Here we pin the gate logic that runs
inside the C callback.
"""
import sys


def test_module_imports_on_all_platforms():
    from locksmith.update import winsparkle_bridge  # noqa: F401


def test_verifier_gate_returns_true_on_pass(tmp_path):
    from locksmith.update.winsparkle_bridge import WinSparkleVerifierGate
    staged = tmp_path / "Locksmith-1.3.0.msi"
    staged.write_bytes(b"fake")

    log_entries = []
    gate = WinSparkleVerifierGate(
        verifier=lambda path, info: True,
        log_recorder=lambda **kw: log_entries.append(kw),
        on_failure=lambda v: None,
    )
    gate.set_release_info({"version": "1.3.0", "anchor_said": "ESAID"})
    gate.set_staged_path(str(staged))
    assert gate.can_shutdown_and_install() is True
    assert log_entries and log_entries[0]["status"] == "verified"
    assert staged.exists()


def test_verifier_gate_returns_false_on_fail_and_deletes(tmp_path):
    from locksmith.update.winsparkle_bridge import WinSparkleVerifierGate
    staged = tmp_path / "Locksmith-1.3.0.msi"
    staged.write_bytes(b"tampered")

    failures = []
    logs = []
    gate = WinSparkleVerifierGate(
        verifier=lambda path, info: False,
        log_recorder=lambda **kw: logs.append(kw),
        on_failure=lambda v: failures.append(v),
    )
    gate.set_release_info({"version": "1.3.0", "anchor_said": "ESAID"})
    gate.set_staged_path(str(staged))
    assert gate.can_shutdown_and_install() is False
    assert not staged.exists()
    assert failures == ["1.3.0"]
    assert logs and logs[0]["status"] == "failed"


def test_verifier_gate_refuses_install_without_staged_path():
    from locksmith.update.winsparkle_bridge import WinSparkleVerifierGate

    called = []
    gate = WinSparkleVerifierGate(
        verifier=lambda *a, **k: called.append("verify") or True,
        log_recorder=lambda **k: None,
        on_failure=lambda v: None,
    )
    gate.set_release_info({"version": "1.3.0"})
    # No set_staged_path call — gate must refuse and NOT invoke the verifier.
    assert gate.can_shutdown_and_install() is False
    assert called == []


def test_verifier_exception_treated_as_failure(tmp_path):
    from locksmith.update.winsparkle_bridge import WinSparkleVerifierGate

    staged = tmp_path / "x.msi"
    staged.write_bytes(b"x")

    def _boom(path, info):
        raise RuntimeError("kel fetch timed out")

    failures = []
    gate = WinSparkleVerifierGate(
        verifier=_boom,
        log_recorder=lambda **kw: None,
        on_failure=lambda v: failures.append(v),
    )
    gate.set_release_info({"version": "1.3.0"})
    gate.set_staged_path(str(staged))
    assert gate.can_shutdown_and_install() is False
    assert failures == ["1.3.0"]


def test_load_dll_returns_none_off_windows():
    if sys.platform == "win32":
        # On Windows the DLL would actually load (or fail); skip here.
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
        verifier=lambda *a, **k: True,
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
