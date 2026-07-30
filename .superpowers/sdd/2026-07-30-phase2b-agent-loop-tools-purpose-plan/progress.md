# SDD ledger — plan: docs/superpowers/plans/2026-07-30-phase2b-agent-loop-tools-purpose-plan.md

Worktree: /Users/seriouscoderone/code/locksmith/.claude/worktrees/assistant-2b
Branch: assistant-2b (from development @ 4ac6336e)
Venv: <worktree>/.venv/bin/python — MINIMAL (pytest + jsonschema only). keri-assistant declares
  `dependencies = []`, so nothing is editable-installed and there is NO `.pth` to collide with:
  the shared-venv hazard in CLAUDE.md is structurally absent here, not merely avoided.
Baseline: 139 tests green. Run from packages/keri-assistant/.
Task order: 1..7 sequentially. NEVER run two implementers at once (git index.lock contention).

## Standing rules for this run (learned from 2A — do not relax)

- **Implementers are assigned ONLY by direct message.** Do NOT create shared task-list entries for
  these tasks. In 2A the task list's own tooling told teammates to self-claim available work, which
  produced a whole task committed outside the review gate; later, setting `owner` to credit finished
  work fired spurious assignment notifications at four released agents. The ledger is the only
  tracker.
- Every dispatch says: do not claim from the task list; never `pip install`; report the real test
  count; if an existing test breaks, STOP and report rather than editing it to green.
- Prefer follow-up commits over amends during fix rounds — an amend destroys the diff that makes the
  correction auditable.
- Sequence review BEFORE dispatching a fix. In 2A I dispatched a fix first and had to correct scope
  mid-flight after the fixer had already committed against the wrong instruction, costing a round.
- **Amending the plan REQUIRES regenerating the affected task brief in the same step.** Missed this
  in 2A and an implementer read a stale golden-pin literal.

## Pre-flight findings (all fixed in 06e0fcf9 BEFORE dispatch)

Audited my own plan the same way 2A's defects were found. Four issues, all the same classes that bit
2A — where the plan text was the defect, not any implementation:

- PF1 four unused imports in test blocks (`ToolRegistry`, `LoopOutcome`, `Grounding`,
  `parse_decision`) — same class as 2A's unused `field` import.
- PF2 Tasks 6/7 imported shared fixtures from another TEST MODULE. Works (pytest resolves it, and
  `test_binding.py` already does `from tests.fakes import`), but it breaks repo convention and
  couples test files. Moved to `tests/fixtures/loop_fixtures.py` + `ScriptedBinding` in `tests/fakes.py`.
- PF3 the `fakes.py` append instructed adding imports Phase 2A **already added** (`ProposalRequest`,
  `ProposalResult`, `EnforcementStrength`) — would have produced duplicate import lines. Verified
  against the real file; instruction now says explicitly not to add them. Task 2's `ToolResult`
  import IS needed (checked: `grep -c ToolResult tests/fakes.py` == 0).
- PF4 synthetic fixtures still carried domain vocabulary. Neutralized
  (`submit_report`/`doc-parse`/`Reporter`/`source_id`), with the *suffix shapes* preserved
  (`*_aid` / `*_id` / `*_said`) because those suffixes are exactly what the grounding tests
  exercise. Task 7's real-corpus block deliberately keeps the vendored real templates — that
  corpus is what caught two Criticals in 2A and synthetic fixtures are what hid them.

Verified after fixing: every code block parses, no undefined names, and zero domain terms anywhere
outside the real-corpus test block.

## Design decisions carried into this plan (do not re-litigate mid-run)

- Decide pass is a **hard-constrained choice-only** schema (action tag + grounded `tool_id` enum +
  bounded answer text). NO tool args, NO command parameters — that is pass 2. The free-text
  alternative is deliberately NOT built; `decide()` is one function so 2D can substitute behind the
  seam and measure tool-call RATE.
- Compute tools are **workbench** tools, host-registered, NOT template-declared (ugard 2026-07-29).
- `ToolExecutor` is deliberately NOT `Dispatcher`. Reads must never travel through `Dispatcher`.
- Loop state is an explicit serializable value (spec §9.13) because the owner requires an approved
  plan to survive an app restart. That persistence lands in 2C; resume must RE-VERIFY the plan SAID
  rather than trust restored state.
- Purpose is SOFT and must never be described or tested as a defence (spec §4.0.1).

## Progress

Task 1 (RoleContext): COMPLETE. 8ea39b62. 145 green (139 + 6).
  Controller verified: 2 files / 89 insertions / 0 deletions, trailer present, role.py verbatim from
  the brief with no extras (no __all__, no __post_init__, no validation), domain audit clean on both
  new files. standing_instruction() is deterministic (pinned by a test) so a backend can reuse its
  KV cache for the prefix. Brief was accurate — no corrections needed.

Task 2 (ToolRegistry): dispatched. BASE = 8ea39b62.
  Dispatch carried the two structural guarantees explicitly, because they are the point of the task
  and are easy to erode later:
    - kind == "exchange" verbs are NEVER tools (authority-bearing work can only become a proposal)
    - ToolExecutor is deliberately NOT Dispatcher; asked for explicit confirmation that tools.py
      contains no reference to Dispatcher at all
  Also handed over the verified pre-flight facts so they are not re-derived: the ToolResult import
  in fakes.py IS needed (grep -c == 0, unlike the three duplicates PF3 caught), and read tools get a
  CLOSED, EMPTY input schema (a projection takes no args this phase; an open schema would let the
  model invent parameters nothing consumes).

Task 2 (ToolRegistry): COMPLETE. feb3d5fa. 159 green (145 + 14).
  Controller verified: 3 files / 231 insertions / 0 deletions; fakes.py PURELY ADDITIVE (only
  RecordingToolExecutor added, the four pre-existing fakes byte-identical); domain audit clean.
  Structural guarantees probed directly, not taken on report:
    exchange verb is a tool?  False    <- authority-bearing work can only become a proposal
    floor verb is a tool?     False
    read tool input_schema    {"type":"object","additionalProperties":false,"properties":{}}  closed
    purpose can only narrow?  True     untagged compute survives?  True
    Dispatcher coupling       NONE — AST-verified (not imported, seams not imported, name unused)

  CONTROLLER PROCESS NOTE — CARRY TO TASK 6. I first ran `grep Dispatcher tools.py`, got a hit, and
  nearly reported the seam guarantee VIOLATED. The hit was the docstring that *documents* the
  guarantee. Grepping for a symbol finds the documentation of a rule as readily as a breach of it;
  only an AST/import check distinguishes them. Same class of error as the C-2 "regression" I wrongly
  flagged in 2A — measuring the wrong property.
  => Task 6's planned invariant `test_the_loop_module_cannot_confirm_or_dispatch` uses
  `inspect.getsource` + substring matching, so it will FAIL on its own explanatory comment if anyone
  writes one, and would PASS if someone reached Dispatcher via an alias. Task 6's implementer must
  assert on imports/calls via AST, not raw source text.

Task 3 (decide pass): dispatched. BASE = feb3d5fa.
  Dispatch spelled out WHY the schema is choice-only (tool suppression: one decode doing both
  action-selection AND argument-shaping can silently stop calling tools while staying schema-valid),
  and named the temptation to add an `args` field as the bug the design exists to avoid.
  Also required: reuse GrammarViolation from proposal.py (one exception type across both passes), and
  OMIT the call_tool alternative when the registry is empty rather than emit an empty enum.

PLAN AMENDED mid-run (cd404748) — seam-isolation invariants now assert on the AST, not source text.
  Trigger: see the Task 2 process note above. My own plan had `assert "Dispatcher" not in
  inspect.getsource(loopmod)` in BOTH Task 5 and Task 6. Wrong in both directions: fails on prose
  explaining the rule, passes on `from .seams import Dispatcher as _D`. Both now walk imports and
  attribute calls. Added mutation row M11 (inject an aliased seams import) so the fixed test must
  PROVE it catches what the substring form would have missed.
  Amending the plan then tripped my own undefined-name scan: Task 6's block used `ast` without
  importing it. Fixed and briefs 5+6 regenerated in the same commit, per the standing rule.

Task 3 (decide pass): COMPLETE. 8dc73a01. 173 green (159 + 14). 2 files, domain-clean, trailer.
  Controller probed every guarantee:
    with tools            ['call_tool','propose','answer']
    empty registry        ['propose','answer']   <- call_tool OMITTED, not an empty enum
    empty enums anywhere  NONE
    no args/payload field True   (pass 1 chooses; pass 2 shapes — the anti-tool-suppression split)
    unknown action / missing action / unregistered tool / no tool_id / empty answer  ALL blocked
    reuses GrammarViolation, defines no competing exception class
  Report said "shared venv's python" — checked rather than skimmed, because a shared venv is a live
  hazard in this repo (absolute-path editable .pth). Benign: correct interpreter, no install, main
  checkout .pth untouched, this worktree has NO __editable__ .pth at all. Told it the accurate phrase
  is "the worktree venv" since that distinction is what matters here.

Task 4 (LoopState): dispatched. BASE = 8dc73a01.
  Dispatch emphasised the one property that matters: state must be a plain immutable
  JSON-round-trippable value (no closures, no generator frames, no in-place mutation), because 2C
  must let a human approve a plan, close the app, reopen, and resume — only possible if state is a
  value. Also to keep the [tool:<id>] marker docstring: that prefix is the data-not-instructions
  signal, and tool output must never be merged into the model's instruction.

Task 4 (LoopState): COMPLETE. eff364ee. 183 green (173 + 10). 2 files / 124 insertions / 0 deletions.
  Controller probed the property the task exists for:
    frozen dataclass          True
    advanced() is pure        True  (old state untouched; a NEW object returned)
    json round-trip exact     True  (no custom encoder needed)
    from_dict missing key     KeyError (rejected)
    observation marker        "[tool:doc-parse] 42 rows" / "[tool:doc-parse] FAILED: timed out"
  Domain-clean. Why it matters more than its size: the exact round-trip is what makes 2C's
  reopen-and-resume possible AT ALL — state in a closure or generator frame cannot be written to
  disk, so 2C would have had to rewrite the loop rather than persist it.

Task 5 (AgentLoop): dispatched. BASE = eff364ee. Largest task; 4 files.
  Dispatch called out the four properties most likely to erode:
    1. the loop must import NOTHING from seams — a proposal LEAVES the loop; 2B does not
       re-implement approval (AST invariant in Task 6 enforces this)
    2. require_hard gates ONLY the propose path — reads/answers must still work on a SOFT binding,
       because helpfulness must not require the hard guarantee
    3. tool output travels in ProposalRequest.data_context, NEVER merged into instruction (a loop
       amplifies injection exposure; this separation is the mitigation)
    4. budget exhaustion is its OWN status — a silent stop is indistinguishable from success
  Also handed over: fakes.py already imports everything ScriptedBinding needs (no new imports —
  do not add duplicates), and the five existing fakes must stay byte-identical.

Task 5 (AgentLoop): COMPLETE. 03077066. 197 green (183 + 14). 4 files / 314 insertions / 0 deletions;
  fakes.py purely additive. Controller verified all four erosion-prone properties:
    Confirmer/Dispatcher/seams imported?  False (AST) ; .dispatch()/.confirm() called?  False
    soft + answer  -> answer               <- helpfulness works on a SOFT binding
    soft + propose -> SoftEnforcementError <- authority does not
    injected text in data_context? True ; leaked into instruction? False
    budget status "budget_exhausted", distinguishable from answer/proposal
  The soft-binding SPLIT is the thing to protect: had require_hard sat at the top of run(), the
  assistant would refuse to READ on a soft backend — useless exactly where helpfulness matters,
  for zero safety gain.

  PLAN DEFECT #1 found by the implementer (mine): test_the_standing_instruction_carries_the_role_purpose
  asserted "Clerk"/"file records" while the ROLE fixture is Reporter/"submit reports" — strings that
  can never co-occur, since standing_instruction() emits the role's own fields verbatim. It fixed the
  ASSERTIONS (right direction; changing the fixture would desync every other ROLE user). Fixed in the
  plan + brief 5 regenerated: de40b7f0.

  CONTROLLER PROCESS ERROR, recorded: to check the fixed assertion bites, I sed-ed a TRACKED fixture
  file in the LIVE worktree while t6 was working in it, then misread stale bytecode as a real
  regression and briefly reported the tree broken. I could have corrupted t6's run. I have been
  careful all session never to run two implementers concurrently for exactly this reason, then did it
  to myself for a probe I did not need — Task 6's mutation pass covers that ground properly, in
  sequence, with reverts. Correct method (used later for M11): feed mutated SOURCE STRINGS to the
  same AST walk, touching no files.

Task 6 (invariants + mutation proof): COMPLETE. da484d09. 207 green (197 + 10). Tree clean.
  ALL 11 MUTATIONS PRODUCED FAILURES — no surviving mutants. Row-by-row table with assertion
  messages is in task-6-report.md; that table is what makes these invariants trustworthy rather
  than decorative.
  Controller re-verified M11 independently (no files touched):
    real loop.py                 invariant PASSES
    aliased Dispatcher as _D     invariant FAILS  <- caught
    from . import seams          invariant FAILS  <- caught (variant not in the brief)
    aliased Confirmer as _C      invariant FAILS  <- caught
    substring form, same mutant  PASSES — MISSES THE BREACH
  So the check I nearly shipped would have declared the seam intact with a Dispatcher import in the
  file. Mechanism (from the implementer): the AST walk records an import's ORIGINAL name, not its
  asname. PRECISION NOTE: I earlier said the substring form "fails on prose explaining the rule" —
  true of tools.py (its docstring names Dispatcher) but NOT of loop.py as written ("confirm
  ceremony"). The demonstrated flaw is the false NEGATIVE; the false positive is latent.

  PLAN DEFECT #2 found by the implementer (mine): Task 6's block imported PARSER from
  loop_fixtures, which defines PARSER_TOOL — ImportError on first collection, and the name was
  unused. It dropped the import rather than edit a shared fixture four modules depend on. Fixed:
  233c08e3.

## METHODOLOGY GAP (root cause of BOTH plan defects this phase)

My scripted domain-neutralization rename desynchronized names ACROSS FILES — once an assertion vs
its fixture (Clerk/Reporter), once an import vs its source module (PARSER/PARSER_TOOL). My
pre-flight validates each code block IN ISOLATION, so it catches unused imports, undefined names,
and syntax within a block, but is structurally blind to:
  - a string literal that disagrees with a fixture defined in another block/file
  - a name imported from a module that does not define it
Added a cross-file import check against loop_fixtures (reports clean). Before any future scripted
rename across a plan, ALSO check assertion/fixture agreement and cross-file imports.
Net for the phase: 2 plan defects surfaced at implementation time (vs 6 in 2A), and NONE reached a
commit — the gate caught both.

Task 7 (real corpus + audit report): dispatched. BASE = da484d09.
  Dispatch drew the distinction that is easy to blur: unconstrained_entity_fields() is VISIBILITY,
  not enforcement — it must NOT guess which free-string fields are credential references, because
  that guess IS the over-broad mechanism we rejected. Asked for the audit's ACTUAL output on both
  real templates, not just that it produces some. Also told the implementer that any mismatch with
  the fixtures/real templates is most likely MY error, to report rather than work around, and to
  prefer fixing the brief over editing a shared fixture.

Task 7 (real corpus + audit): COMPLETE across 4 commits — 0104a7f3, 235ee187, 441bf1a0, 3bc65faf.
  232 green. ALL 7 TASKS DONE.

  PLAN DEFECT #3, found by the implementer and the best catch of the phase (mine):
  audit_schema's docstring called the plural `_saids` shape "the decisive one" while `_walk` only
  reported type:"string" leaves — so the detector was STRUCTURALLY BLIND to the very example the
  docstring called decisive. An overclaim inside the module whose entire purpose is honest
  visibility, and a correctness gap (a required array of credential refs is at least as forgeable as
  a single one — one bad element suffices). Nobody asked it to check docstring-vs-coverage.
  Verified by controller: declaration_saids is NOT in either vendored template (it lives in
  chief-underwriting-officer-approves-product-launch, unvendored); its shape is type=array,
  items=string; and pre-fix the detector reported only the sibling plain-string field.

  CONTROLLER FINDING that fixed the fix: measuring the audit output showed 55 rows / 1 genuine hit
  = 2% signal. As specified it delivered the FORM of visibility without the substance — nobody reads
  55 rows of timestamps and prose to find one item. Root cause: I specified "all unconstrained free
  strings" when the actual detector used to FIND the original defect was the template author's own
  DESCRIPTION. Added claimed_credential_refs with two signals, validated before specifying:
    A: own description matches SAID|self-addressing|digest  -> grant_license.application_id
    B: leaf name matches an A hit in the same surface       -> spurn_application.application_id
    carrier 2 hits / 0 noise ; actuary 0 (correct — its refs are properly named *_said and excluded
    upstream by grounded_set_for before becoming candidates)
  NEW FINDING: the corpus contains TWO instances of the defect, not one. spurn_application
  .application_id has NO description at all, so only signal B can see it.
  EVIDENCE that the earlier _id-widening rejection was right: 7 product_id + thread_id fields are
  ordinary opaque identifiers whose own descriptions say so ("Stable kebab-case product
  identifier", "the designer's negotiation thread"). Widening would have deleted legitimate
  commands from surfaces. That was a judgement call before; it is evidence now.

  The implementer's `shards` observation SHARPENED the array fix rather than merely flagging a limit,
  and prevented a false positive:
    array items = bare STRING -> IS a gap   (declaration_saids)
    array items = OBJECT      -> NOT a gap  (shards; its shard_said leaf is already grounded)
  Controller verified all four cases + that the real-corpus signal list stayed byte-identical
  (broad gained exactly one true positive, open_rate_program.states).
  It also wrote the tests first and got exactly ONE failure, proving the "neither vendored template
  has a plural field" claim was already true pre-fix — pinned by a test, not asserted in prose.

## CONTROLLER PROCESS ERROR — MESSAGE/COMMIT CROSSINGS (4 this run)
Four times I verified, found something, and dispatched while an implementer was mid-commit; each
message was accurate when sent and stale on arrival. Cost: one round trip each. No wrong code
resulted, because the implementers checked HEAD rather than trusting my description of it. One
crossing mattered more: HEAD moved 441bf1a0 -> 3bc65faf AFTER I generated the reviewer's diff and
dispatched it — the exact drift that confused a reviewer in 2A. I sent review-2b the delta
immediately rather than let it rediscover it.
FIX FOR 2C: verify to completion, THEN send one consolidated correction. Do not dispatch mid-verify.

## PHASE 2B SUMMARY — 16 commits 4ac6336e..3bc65faf, 19 files, +3330/-7, 232 green, tree clean
Plan defects found at implementation time: 3 (vs 6 in 2A). NONE reached a commit — the gate caught
all three. All three trace to MY plan, not to any implementer's transcription:
  #1 assertion checking strings its fixture could never produce (scripted-rename desync)
  #2 import of a name the fixture module does not define  (scripted-rename desync)
  #3 docstring claiming coverage the code did not have    (spec-vs-implementation drift)
Methodology gap named: my pre-flight validates each code block IN ISOLATION, so it is blind to
cross-file disagreement (assertion vs fixture, import vs source module) and to docstring-vs-code
coverage claims. Cross-file import check added. Whole-branch review dispatched (review-2b, opus).
NOT MERGED, NOT PUSHED — awaiting the owner's go. Base branch is `development`.

## WHOLE-BRANCH REVIEW (review-2b, opus): MERGE AFTER C1 + I1. 1 Critical, 4 Important, 8 Minor,
## plus 4 correct-but-unpinned findings. All four requested areas covered; reverts confirmed with a
## .pyc count (a stale .pyc had already produced one false result in this run).

  C1 (CRITICAL, controller-reproduced): a projection whose id equals a command's id puts an
    AUTHORITY-BEARING verb id into the autonomous tool registry.
      verbs [('grant','exchange'),('grant','query')] -> registry ('grant',)
      exchange ids that ARE tools: {'grant'} ; surface.by_id('grant').kind = exchange ; no raise
    Cause: build_micro_app_surface merges commands[]+projections[] with NO cross-list id check, and
    actionschema's duplicate-id raise sits behind `if verb.kind != "exchange": continue`, so it
    structurally cannot see a query-vs-command collision. Loop would then execute("grant", {}) with
    no require_hard, no proposal, no ceremony.
    WHY CRITICAL: tools.py's docstring PROMISES the host that exchange verbs are never tools, and
    three tests assert it — all with disjoint ids. Reviewer's framing, which is the right one: every
    other finding is a bug the host would eventually observe; this one is a bug the host is actively
    TOLD cannot exist. Also the only finding that gets harder with time.

  I1 (blocking, controller-reproduced): read tools send the #25923 empty-object schema as the ENTIRE
    request schema — the hazard OUR OWN actionschema docstring warns about, on a path no test
    touches. Research deferred #25923 to 2D but scoped to the proposal PAYLOAD (one branch of a
    oneOf); here it is the whole schema, so if the bug bites EVERY projection read fails, not one
    branch. Root cause: all 11 CALL_TOOL sites in the suite name a COMPUTE tool, so the read path
    had never been executed. Also wastes a full decode asking the model to emit {}.

  I5: AgentLoop takes registry and role independently and never applies filtered_for itself, so a
    host that forgets role= gets the FULL workbench tool set with the narrow standing instruction —
    no error. One-line fix converts a host-error class into an impossibility.
  I4: _SAID_CLAIM's re.IGNORECASE makes \bSAID\b match ordinary legalese ("the said applicant"), and
    signal B then amplifies each false positive across same-named siblings. Latent on this corpus
    (0 hits) but the filter's whole value is a reviewer trusting a 2-row list.
  I2 (DEFERRED, reasons): model-produced TOOL ARGS get neither the hard gate nor any parse layer —
    extra keys survive additionalProperties:false, wrong types pass, an ungrounded *_aid rides in.
    Not an authority-guarantee violation (§4.0.1: workbench acts need no hard constraint) but the one
    place the library hands unvalidated model output onward. ~15 lines; do in 2C.
  I3 (DEFERRED, needs a decision first): max_iterations is UNREACHABLE as shipped (iteration
    increments only on the tool path, so iteration==tool_calls and 6<8 means it never fires); and
    both checks sit at the loop top, so hitting the tool cap discards the Nth observation it just
    paid for. Its test passes only by inverting the shipped relationship. Fix needs a decision about
    what an "iteration" counts (model calls vs cycles) — do not code it blind.

  CORRECT-BUT-UNPINNED (the ask that paid off best):
  A1: deleting the never-verb guard from surface.py's PROJECTIONS loop leaves all 232 tests passing.
      2A barely needed it; 2B made it load-bearing by turning projections into the AUTONOMOUS read
      space. The look-alike test uses a COMMAND with a /keri/cmd/rotate_key route, so it passes for
      an unrelated reason. Guard works today; zero coverage.
  A2: both injection tests script -> ANSWER, so the inspected request is always the DECIDE pass. The
      pass that actually produces authority-bearing output is uncovered. Holds today.
  A3: test_a_soft_binding_is_FINE_for_reads_and_answers never calls a tool — the "reads" half of its
      name is unpinned, and that is exactly where I2 bites.
  m1: the invariant test for purpose-cannot-widen passes against a no-op filter (role tags are a
      superset, so filtered==unfiltered satisfies <=). Property IS covered in test_tools.py
      (reviewer verified that one fails against the stub). Weak assertion, not a hole.

  Reviewer's characterisation of this branch's weakness, better than mine: "coverage that stops at
  the boundary of the thing it names." 2A's failure mode did NOT recur at scale — it independently
  re-derived M1/M3/M10 and all bite as tabled.

  SPEC CLAIMS VERIFIED IN CODE: §4.0.1 purpose-is-not-a-control HOLDS (RoleContext's only effects
  are prompt text and filtered_for; nothing in loop.py branches on it) — which is why I5 is
  Important-not-Critical and m8 is Minor. §4.2 partition holds for reads/compute, BREAKS for
  authority-bearing via C1. §9.13 serialisable state HOLDS.

  fix-2b dispatched with: C1, I1, I5, I4 + m1/m2/m3/m6 + tests A1/A2/A3.
  Dispatched AFTER verifying to completion — first round this phase with no message/commit crossing.

## FIX ROUND COMPLETE: 9214f6bf. 242 green (232 + 10). Tree clean. 8 files, +210/-17.
  Controller verified every item independently BEFORE the report arrived:
    C1  collision -> ValueError ; __clarify__ -> ValueError ; disjoint ids -> builds
    I1  read-tool path: 2 backend calls (arg decode skipped), executor got {}, no empty-object schema
    I5  unfiltered registry + narrow role -> model offered ['board'] only; send-email leaked? False
    I4  "the said applicant filed" -> quiet ; "SAID of the prior record" -> reported
    m3  copy.deepcopy(_NO_ARGS) with the aliasing rationale in a comment
    corpus signal list UNCHANGED: carrier 2, actuary 0  (fix removed false-positive CAPACITY, not signal)
  A1/A2/A3 pinning tests present. m1 tightened with a narrow role. m2 docstring overclaim corrected.

## OWNER DECISIONS 2026-07-30 (final for this phase)
  1. KEEP THE BRANCH AS-IS. assistant-2b @ 9214f6bf is NOT merged and NOT pushed. Worktree preserved.
     development untouched by 2B.
  2. I2 (tool-arg validation) and I3 (budget rework) BOTH scheduled into 2C — recorded on development
     as spec verify-items 14 and 15 (commit d81eae6d, docs only, currently UNPUSHED).
     Item 15 deliberately records the DECISION THAT MUST PRECEDE CODE — does an "iteration" count
     backend calls or loop cycles? Coding it blind is how the unreachable limit arose in the first place.

## CONTROLLER ERROR found while writing items 14/15: THE WORKTREE'S SPEC WAS STALE.
  assistant-2b branched from development @ 4ac6336e; I then committed defb0c26 (§4.0.1 three-layer
  model + verify-item 13) to the MAIN checkout. So the worktree never contained the §4.0.1 or §9.13
  sections the 2B plan cites. No implementer was blocked — every dispatch quoted the content inline and
  the plan's Global Constraints carried it — but my earlier statement that those references were
  readable from the worktree was WRONG. Items 14/15 therefore went to development, where 13 lives.
  LESSON: when a worktree exists, decide which checkout owns shared design docs and edit only there.

## DURABILITY NOTE
  .superpowers/sdd/ is GITIGNORED by design (scratch). This ledger and all 7 task reports + the fix
  report exist ON DISK ONLY, inside this worktree. Everything decision-bearing has been promoted into
  tracked artifacts (spec verify-items 10-15, the plan). The ledger's unique content is the PROCESS
  record, and it survives only because the owner kept this worktree. Removing the worktree takes it.
  (The 2A ledger is already gone for exactly this reason — that worktree was deleted.)

## PHASE 2B FINAL: 17 commits, 242 green. What generalises, for 2C:
  - The mutation-proof requirement WORKED: 11/11 bit, and the reviewer independently re-derived 3 rows.
    It is the single practice that most distinguishes 2B from 2A.
  - The sharpest findings came from asking "is this guarantee PINNED?" not "does this WORK?":
    deleting the projection never-verb guard left all 232 tests passing; the read-tool path had never
    once been executed despite 11 tool-call tests. Both were correct code with zero coverage —
    invisible to a green suite. Reviewer's phrase for it: "coverage that stops at the boundary of the
    thing it names."
  - 3 plan defects surfaced at implementation time (vs 6 in 2A), NONE reached a commit. All 3 were mine.
  - My pre-flight validates each code block IN ISOLATION -> blind to cross-file disagreement and to
    docstring-vs-code coverage claims. Cross-file import check added; the docstring class still needs a
    reader.
  - 4 message/commit crossings, all from dispatching mid-verification. The final round verified to
    completion first and had none. Do that from the start in 2C.
