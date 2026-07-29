# The harness can't read list rows rendered as custom item widgets

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** medium (harness capability gap; blocks asserting on a common Qt pattern)

## What we saw

`get_list_items` returns `it.text()` for each `QListWidgetItem`
(`~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py:716-723`). Locksmith's
paired-peers list — like any richly-rendered list — builds each row with
`setItemWidget()` and deliberately leaves the item's own text empty, because Qt paints
both the item text and the widget and they overlap
(`ui/vault/settings/peer_section.py:413-421`). So the harness reported one row with
`text: ""` for a row that visibly reads `alice@A   EAB…3Kx   tcp://192.168.1.42:5621`.

The test asserting on that row had been failing on `development` and the failure
(`assert 'alice@A' in ''`) reads like a data bug in the peer record, not a harness
limitation.

Worked around Locksmith-side in `8663c1d6` by giving the row labels objectNames
(`peerSettingsSection.peerRowPrimary` / `.peerRowHealth`) so `get_text` can reach them.
That is a fine convention to keep — named widgets are how everything else here is
addressed — but it does not fix the general case, and the next custom-widget list will
hit the same wall.

## The actual work

In the harness (generic, not feature-coupled — this is "read what the user sees in a
list", which is exactly the harness's job):

1. `get_list_items` should fall back to the item widget's rendered text when
   `it.text()` is empty: `widget.itemWidget(it)`, then join the text of its descendant
   `QLabel`s in visual order. Include it as a separate field (e.g. `widget_text`) rather
   than overloading `text`, so existing assertions don't silently change meaning.
2. Same treatment for `get_table_rows` with `setCellWidget`.

Harness changes land on the harness branch first, then cherry-pick (memory
`feedback_harness_first`). Note the tests read the harness from the host install at
`~/.locksmith/plugins`, so a harness change needs that install refreshed to take
effect — which is shared state across worktrees.

## Evidence / references

- `~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py:697-723`
  (`_op_get_list_items`), `:725+` (`_op_get_table_rows`)
- `src/locksmith/ui/vault/settings/peer_section.py:403-447`
- `tests/integration/peer/test_pair_via_ui.py`
- Memory: `reference_ui_harness_cypress`, `feedback_harness_human_only`,
  `feedback_harness_first`, `reference_object_name_convention`
