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
