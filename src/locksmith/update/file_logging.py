"""Diagnostic file logging for the Locksmith updater.

On Windows, GUI apps have no console stderr, so update-path log lines
([update] …, native_updater.*, winsparkle.*) are invisible at runtime.
This module attaches a rotating file handler under the per-OS app data
directory so those lines land on disk for post-hoc diagnosis.

The handler integrates with keri's hio.help.ogling.Ogler, which uses
``propagate=False`` on every logger it vends and attaches its own
``baseConsoleHandler`` directly.  To reach all ogler-managed loggers we:

1. Add the file handler to every existing logger that carries
   ``ogler.baseConsoleHandler``.
2. Wrap ``ogler.getLogger`` so all future loggers also receive it.

``setup_file_logging()`` is idempotent — safe to call at startup without
checking whether it was already called.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from keri import help as _keri_help

from locksmith.update.log import _app_data_base as _app_data_dir

# ---------------------------------------------------------------------------
# Sentinel attribute name on the ogler singleton
# ---------------------------------------------------------------------------

_HANDLER_ATTR = "_locksmith_diag_file_handler"  # sentinel attr on the ogler


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_file_logging() -> Path:
    """Attach a rotating file handler to all ogler-managed loggers.

    Returns the path to the log file.  Safe to call more than once;
    subsequent calls are no-ops that return the same path.
    """
    ogler = _keri_help.ogler

    # Idempotency: if we already attached a handler, return its path.
    existing: logging.handlers.RotatingFileHandler | None = getattr(
        ogler, _HANDLER_ATTR, None
    )
    if existing is not None:
        return Path(existing.baseFilename)

    # Build the intended log path (returned even on failure so the call site
    # can log it — the value is only used for informational logging in main.py).
    log_dir = _app_data_dir() / "logs"
    log_path = log_dir / "locksmith_update.log"

    try:
        # Create the directory and open the handler.  On locked-down Windows
        # installs or sandboxed macOS apps this can raise OSError/PermissionError;
        # we must not let it crash app startup.
        log_dir.mkdir(parents=True, exist_ok=True)

        # Build the handler.
        fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)-8s %(message)s")
        fmt.default_msec_format = None
        handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=1 * 1024 * 1024,  # 1 MiB per file
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(fmt)
        # Emit everything the ogler-level is configured to emit.
        handler.setLevel(logging.NOTSET)

        # Store the handler on the ogler so idempotency check above works and
        # so close() can clean up on Windows (mirrors ogler's own pattern).
        setattr(ogler, _HANDLER_ATTR, handler)

        # --- Attach to all currently existing ogler-managed loggers -----------
        _attach_to_existing(ogler, handler)

        # --- Wrap ogler.getLogger so future loggers also get the handler ------
        _patch_ogler_get_logger(ogler, handler)

    except OSError as exc:
        print(f"file_logging: disabled ({exc})", file=sys.stderr)

    return log_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _attach_to_existing(ogler, handler: logging.Handler) -> None:
    """Add *handler* to every existing logger that carries ogler's console handler."""
    console = ogler.baseConsoleHandler
    for name in list(logging.root.manager.loggerDict):
        lg = logging.getLogger(name)
        if console in lg.handlers and handler not in lg.handlers:
            lg.addHandler(handler)


def _patch_ogler_get_logger(ogler, handler: logging.Handler) -> None:
    """Wrap ogler.getLogger so future calls also attach *handler*."""
    original_get_logger = ogler.getLogger.__func__  # unbound method

    def _patched_get_logger(self, name=None, level=None):
        # Call the original (which sets propagate=False, attaches console/file handlers).
        if name is None:
            lg = original_get_logger(self)
        else:
            lg = original_get_logger(self, name, level) if level is not None else original_get_logger(self, name)
        # Add our diagnostic handler if not already present.
        if handler not in lg.handlers:
            lg.addHandler(handler)
        return lg

    import types
    ogler.getLogger = types.MethodType(_patched_get_logger, ogler)
