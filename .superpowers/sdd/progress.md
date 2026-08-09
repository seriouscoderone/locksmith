# Copy Error Affordance — SDD Progress

Plan: docs/superpowers/plans/2026-07-21-copy-error-affordance.md
Branch: copy-error-affordance
Base (before Task 1): 94a797d

> NOTE 2026-08-08: this file was accidentally overwritten by a later SDD run and
> reconstructed from a copy read earlier in that session. The task lines and
> commits below are verbatim; treat the Minor-findings wording as faithful but not
> byte-exact. The commits it names are the authority — they are all in git.

- Task 1: complete (commit ca63ac7, review clean — spec ✅, 0 Critical/Important)
- Task 2: complete (commit a8edb41, review clean — spec ✅, 0 Critical/Important; eventFilter no-collision + no-reflow verified)
- Task 3: complete (commit 1020837, review clean — spec ✅, 0 findings; page banner twin of dialog)
- Task 4: complete (commit 5552c14, review clean — spec ✅, 0 findings; copy content derived live from labels)
- Task 5: complete (commits 5bdd0b1..3ac4faa, review clean — spec ✅; brief test/Qt contradiction fixed: idiomatic setWindowTitle + honest assertions)
- Task 6: complete — 11/11 new focused tests pass; 15/15 regression dialog tests pass; all 11 copy-button-caller + edited modules import OK. Only noise = pre-existing pysodium DeprecationWarning (third-party, not ours).

## Minor findings (for final review triage)
- Task 1 Minor: buttons.py `icon_color` gated with `if icon_color:` (truthiness) not `is not None`; empty-string would behave like None. No caller passes ''. Cosmetic.
- Task 5 Minor (final review): `copied` signal now emitted for all callers, consumed by none of the 6 legacy sites — harmless dead surface.
- Cross-cut Minor (final review): banner duplication (eventFilter+opacity+wiring identical) across dialogs.py/page.py — acceptable (2 distinct base classes, identical blocks); extract a HoverRevealCopyMixin only if a 3rd banner appears.
- Cross-cut Minor (final review): checkmark confirmation can be hidden early if user leaves banner within 1200ms — cosmetic, copy already done.
