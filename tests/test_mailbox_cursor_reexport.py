"""The Locksmith mailbox_cursor path must re-export the library's DbTopsCursorStore
(same object), so existing importers keep working after the promotion."""


def test_reexports_the_library_class():
    from locksmith.core.mailbox_cursor import DbTopsCursorStore as Local
    from keri_serverless_mailbox import DbTopsCursorStore as Lib
    assert Local is Lib
