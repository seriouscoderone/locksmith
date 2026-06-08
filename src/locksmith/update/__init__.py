"""Update verification subsystem for Locksmith.

Consumes the appcast + publisher KEL + witness receipts and gates artifact
installation by SHA256 match against the anchored release seal. Public
surface used by Phase 5's Sparkle UI:

- ``verify.verify_artifact(...)``
- ``staging.stage_and_lock(...)``
- ``log.append_entry(...)`` / ``log.read_entries(...)``
- ``errors.UpdateError`` and subclasses
"""
