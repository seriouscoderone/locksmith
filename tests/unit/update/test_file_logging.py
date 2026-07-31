"""Tests for ``locksmith.update.file_logging.setup_file_logging``.

The file handler must:
- Return a Path under the app data dir (monkeypatched to tmp_path).
- Write log lines emitted through the keri ogler (same mechanism the app uses).
- Be idempotent: a second call must not duplicate the handler or raise.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from keri import help

from locksmith.update.file_logging import _HANDLER_ATTR


@pytest.fixture(autouse=True)
def _reset_file_logging_state():
    """Reset ogler singleton state BEFORE and after each test.

    Remove the sentinel attribute that signals a handler is attached and delete
    the instance-level ``getLogger`` override so the class method is restored.
    Resetting *before* matters too: importing ``locksmith.main`` (e.g. via the
    splash test) runs ``_setup_file_logging()`` at module import, which would
    otherwise leave the sentinel + patched getLogger in place before the first
    test here — making ``setup_file_logging()`` idempotent, silently skipping
    the per-test ``tmp_path`` monkeypatch, so tests pass only by ordering.
    """
    def _reset():
        ogler = help.ogler
        # Remove the sentinel handler attribute (also closes the open file
        # handle so Windows does not lock the tmp_path).
        handler = getattr(ogler, _HANDLER_ATTR, None)
        if handler is not None:
            handler.close()
            delattr(ogler, _HANDLER_ATTR)
        # Restore the class-level getLogger by removing the instance-level
        # override set by _patch_ogler_get_logger() (a bound MethodType on the
        # instance); deleting it unmasks the class method.
        try:
            del ogler.getLogger  # type: ignore[attr-defined]
        except AttributeError:
            pass  # was never patched (e.g. OSError path), nothing to undo

    _reset()
    yield
    _reset()


def test_setup_file_logging_returns_path_under_data_dir(tmp_path, monkeypatch):
    """Returned path must be under the monkeypatched data dir."""
    from locksmith.update import file_logging

    monkeypatch.setattr(file_logging, "_app_data_dir", lambda: tmp_path)
    log_path = file_logging.setup_file_logging()

    assert isinstance(log_path, Path)
    assert str(log_path).startswith(str(tmp_path))


def test_setup_file_logging_writes_ogler_lines(tmp_path, monkeypatch):
    """A line logged via ogler.getLogger must appear in the log file."""
    from locksmith.update import file_logging

    monkeypatch.setattr(file_logging, "_app_data_dir", lambda: tmp_path)
    log_path = file_logging.setup_file_logging()

    # Mirror what main.py does at startup: set ogler level to INFO so that
    # info-level lines from [update]/native_updater/winsparkle are emitted.
    help.ogler.level = logging.INFO

    # Use the same mechanism the app uses.
    lg = help.ogler.getLogger(__name__)
    lg.info("[update] diagnostic test line sentinel_abc123")

    # Flush all handlers on this logger.
    for handler in lg.handlers:
        handler.flush()

    content = log_path.read_text(encoding="utf-8")
    assert "sentinel_abc123" in content


def test_setup_file_logging_idempotent(tmp_path, monkeypatch):
    """Calling setup_file_logging twice must not double-add the handler."""
    from locksmith.update import file_logging

    monkeypatch.setattr(file_logging, "_app_data_dir", lambda: tmp_path)
    file_logging.setup_file_logging()
    file_logging.setup_file_logging()

    lg = help.ogler.getLogger(__name__)
    # Count only the file handlers pointing at our log file.
    from logging.handlers import RotatingFileHandler

    diag_handlers = [
        h for h in lg.handlers if isinstance(h, RotatingFileHandler)
    ]
    assert len(diag_handlers) == 1


def test_setup_file_logging_does_not_remove_console_handler(tmp_path, monkeypatch):
    """The existing ogler console handler must still be present after setup."""
    from locksmith.update import file_logging

    monkeypatch.setattr(file_logging, "_app_data_dir", lambda: tmp_path)
    file_logging.setup_file_logging()

    lg = help.ogler.getLogger(__name__)
    console_handlers = [h for h in lg.handlers if h is help.ogler.baseConsoleHandler]
    assert len(console_handlers) == 1


def test_log_path_comes_from_the_brand(tmp_path, monkeypatch):
    """The diagnostic log is per-brand: the directory comes from
    branding.app_data_dir() and the filename from the brand id, so a
    Usurance install's trail never lands in (or overwrites) Locksmith's."""
    from locksmith.core import branding
    from locksmith.update import file_logging

    monkeypatch.setattr(file_logging, "_app_data_dir", lambda: tmp_path)
    cfg = tmp_path / "brand.json"
    cfg.write_text('{"id": "usurance", "display_name": "Usurance"}')
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(cfg))
    branding._reset_cache_for_tests()
    try:
        log_path = file_logging.setup_file_logging()
    finally:
        monkeypatch.delenv("LOCKSMITH_BRAND_CONFIG", raising=False)
        branding._reset_cache_for_tests()

    assert log_path.name == "usurance.log"


def test_default_wiring_reads_the_brand_app_data_dir():
    """setup_file_logging's directory seam must BE branding.app_data_dir —
    otherwise the per-brand path exists but the log doesn't use it."""
    from locksmith.core import branding
    from locksmith.update import file_logging

    assert file_logging._app_data_dir is branding.app_data_dir


def test_peer_diagnostic_lines_land_in_the_file(tmp_path, monkeypatch):
    """The reason this file exists post-live-test: peer.send.* lines from an
    installed/Finder-launched build must be diagnosable after the fact
    (backlog/2026-07-29-grant-send-reports-success-while-undeliverable.md
    item 3). The peer modules were imported long before setup ran — the
    attach-to-existing path must cover their loggers."""
    from locksmith.update import file_logging

    monkeypatch.setattr(file_logging, "_app_data_dir", lambda: tmp_path)
    # Ensure the logger exists BEFORE setup, like a real import order can.
    import locksmith.peer.sending  # noqa: F401 — creates the ogler logger

    log_path = file_logging.setup_file_logging()
    help.ogler.level = logging.INFO

    lg = help.ogler.getLogger("locksmith.peer.sending")
    lg.setLevel(logging.INFO)
    lg.warning(
        "peer.send.peer_failed recipient=Etest endpoint=tcp://10.0.0.9:5622 "
        "err=timed out sentinel_peer_diag")
    for handler in lg.handlers:
        handler.flush()

    assert "sentinel_peer_diag" in log_path.read_text(encoding="utf-8")


def test_rotation_cap_is_a_few_megabytes(tmp_path, monkeypatch):
    """Pinned so a future edit doesn't silently balloon the on-disk
    footprint (or shrink it below diagnosability): 2 MiB per file, 3
    backups — ≤8 MiB worst case."""
    from logging.handlers import RotatingFileHandler

    from locksmith.update import file_logging

    monkeypatch.setattr(file_logging, "_app_data_dir", lambda: tmp_path)
    file_logging.setup_file_logging()

    handler = getattr(help.ogler, file_logging._HANDLER_ATTR)
    assert isinstance(handler, RotatingFileHandler)
    assert handler.maxBytes == 2 * 1024 * 1024
    assert handler.backupCount == 3
