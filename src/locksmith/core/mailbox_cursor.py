"""Re-export DbTopsCursorStore from the shared keri-serverless-mailbox library.

The implementation moved to keri_serverless_mailbox.cursor_store so the concierge-api
CLI host and the Locksmith wallet share one class. This module keeps the historical
import path (locksmith.core.mailbox_cursor.DbTopsCursorStore) stable for existing
importers (core/indirecting.py, tests)."""
from keri_serverless_mailbox import DbTopsCursorStore

__all__ = ["DbTopsCursorStore"]
