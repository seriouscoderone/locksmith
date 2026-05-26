## Summary

`LocksmithTextListWidget` (`src/locksmith/ui/toolkit/widgets/text_list.py`) calls `self._dialog._resize_to_content()` after every add / remove / clear-all. No dialog in the codebase defines `_resize_to_content` — not `LocksmithDialog`, not `CreateIdentifierDialog`. When the witness flow added by PR #74 calls `LocksmithTextListWidget.set_dialog(self)`, the first user-triggered add raises:

```
Traceback (most recent call last):
  File "src/locksmith/ui/toolkit/widgets/text_list.py", line 146, in _add_item
    self._dialog._resize_to_content()
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'CreateIdentifierDialog' object has no attribute '_resize_to_content'
```

End-user effect: the AID-create dialog visually accepts the witness (the AID label appears in the list), but the dialog state is corrupted by the exception, and subsequent submit attempts fail with *"Alias is required"* even when the alias field was populated. The witness flow PR #74 is end-to-end broken on its happy path.

## Reproduction (via the wallet UI)

1. Launch wallet, open a vault.
2. Resolve a non-transferable witness AID's OOBI via *Remote Identifiers → Add Contact* (so its KEL lands in `hby.kevers`).
3. *Local Identifiers → Add Identifier*.
4. Fill alias.
5. Expand **Advanced Configuration → Witnesses**.
6. Paste the witness AID into the "Witness AID prefix" field.
7. Click the **Add item** (+) button.
8. AttributeError thrown immediately.

Reproduced on `main` of `feat/designer-plugin-spec` (carrying PR #74) and on a `dev` integration branch carrying #74 + the plugin framework.

## Reproduction (programmatic, via the `locksmith-ui-tester` plugin)

```bash
.venv/bin/python -m locksmith_ui_tester.cli click '{"target": "Add Identifier"}'
.venv/bin/python -m locksmith_ui_tester.cli type '{"target": "FloatingLabelLineEdit:0", "text": "Test Witnessed AID"}'
.venv/bin/python -m locksmith_ui_tester.cli click '{"target": "Witnesses"}'
.venv/bin/python -m locksmith_ui_tester.cli type '{"target": "FloatingLabelLineEdit:2", "text": "BNbRfMPQQge6wKO0uof9Y0e_QYOfiF08k9drc6pOgzjt"}'
.venv/bin/python -m locksmith_ui_tester.cli click '{"target": "Add item"}'   # ← traceback here
```

## Root cause

Three call sites in `src/locksmith/ui/toolkit/widgets/text_list.py` all do the same thing:

```python
# line 144-146 (after _add_item)
if self._dialog:
    self._dialog._resize_to_content()

# line 211-212 (after _remove_item)
if self._dialog:
    self._dialog._resize_to_content()

# line 263-264 (after clear)
if self._dialog:
    self._dialog._resize_to_content()
```

The `if self._dialog` guard checks presence, not capability. The widget's `set_dialog(dialog)` (line 266) accepts any dialog without verifying it implements the contract.

A grep for `_resize_to_content` across the codebase finds only the three call sites in `text_list.py` and no definition anywhere:

```
$ grep -rn "_resize_to_content" src/
src/locksmith/ui/toolkit/widgets/text_list.py:146
src/locksmith/ui/toolkit/widgets/text_list.py:212
src/locksmith/ui/toolkit/widgets/text_list.py:264
```

`paginated.py` has a similarly-named `_resize_table_to_content` (different name, different class).

## Why no existing test caught it

`text_list.py` was added in the initial port (`ea50b935 Initial locksmith port for keri foundation`) and has not been modified since. PR #74 (witnesses-at-inception) is the first consumer that calls `LocksmithTextListWidget.set_dialog(...)` and then drives an interactive add. The widget's own tests (if any) likely never exercised the dialog-coupled path, so the missing-method invariant slipped through.

Other consumers of `LocksmithTextListWidget` (if any exist) either do not call `set_dialog`, or call it with a dialog object that happens to tolerate the AttributeError without surfacing.

## Suggested fix shape

Two viable approaches:

**A. Guard with `hasattr` at the call sites** (minimal, no dialog changes):

```python
if self._dialog and hasattr(self._dialog, "_resize_to_content"):
    self._dialog._resize_to_content()
```

Three lines. The widget falls back to its default (non-animated) sizing for dialogs that don't support the contract. Witness adds no longer crash.

**B. Add `_resize_to_content` to `LocksmithDialog`** as the intended contract:

```python
# LocksmithDialog
def _resize_to_content(self) -> None:
    self.adjustSize()
```

(Or a proper animated resize using the `dialogHeight` Qt property that `CollapsibleSection.set_dialog` already animates via `QPropertyAnimation(dialog, b"dialogHeight")` — see `collapsible.py:95`.)

Option B is the better long-term fix because it gives the user the intended animated growth/shrink as items come and go; the widget's call site naming clearly anticipated a defined method, not a duck-typed hasattr probe. Option A is the safe one-line patch that unblocks PR #74 today.

A combination — `LocksmithDialog` defines a sensible default `_resize_to_content` AND the text_list call sites grow `hasattr` guards for non-conforming dialogs — is even safer.

## Tests that should be added with the fix

- Unit test: `LocksmithTextListWidget` with a stub dialog that does NOT implement `_resize_to_content` — `_add_item` succeeds without raising (guarded path).
- Unit test: `LocksmithTextListWidget` with a `LocksmithDialog` parent — `_add_item` triggers the dialog's `_resize_to_content` (if Option B taken).
- Visual / integration test: open `CreateIdentifierDialog`, expand Witnesses, add a valid witness AID, click Create — confirm the new AID's KEL has `b=[<witness AID>]` and `bt=1` for `toad=1`.

## Environment

- Branch: `dev` (carries #74 + plugin framework cherry-pick) — also reproduced on `feat/designer-plugin-spec`.
- Python 3.14.1, `keri==2.0.0.dev6`.
- macOS 25.4, arm64.
