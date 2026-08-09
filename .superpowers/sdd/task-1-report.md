# Task 1 Report — Read the payload schema from the EGF

**Status:** DONE_WITH_CONCERNS (see §4 — a real data-order bug was found and fixed;
the coordinator should sanity-check my fix, and downstream tasks should know the
`brands/usurance/egf/` template's `properties` order is not the declared order).

**Commit:** `9bdf0cfb52efebfcde89e500c23cfde9e04f5d56` on `claude/cuo-mandate-form`.

**Test summary:** `9 passed` (brief said 8; corrected to 9 per the coordinator's added
guard test — see §2).

## 1. What was implemented

- `src/locksmith/plugins/cuo/schema_source.py` — `SchemaSourceError`,
  `FieldConstraints`, `MandateSchema`, `load_mandate_schema()`, `CUO_ROLE_ID`,
  `DECLARE_COMMAND_ID` — matches the brief verbatim **except** the `order`
  derivation inside `load_mandate_schema`, which had to change; see §3. No schema
  literal appears in this file (verified by grep, §5).
- `tests/plugins/cuo/__init__.py` — empty package marker, verbatim.
- `tests/plugins/cuo/test_schema_source.py` — the brief's 8 tests verbatim, plus the
  coordinator's `test_the_brand_fixture_actually_activated_an_egf_dir` guard test
  appended at the end.
- `tests/plugins/cuo/conftest.py` — **new file, not in the brief's original file
  list.** Added on the coordinator's explicit instruction after I reported the
  brand-activation gap (see §2). Autouse fixture that builds the usurance release
  bundle if the gitignored `src/locksmith/release/usurance/` doesn't exist yet
  (mirroring `tests/conftest.py:15-21`'s `_build_default_bundle`), then activates it
  via `LOCKSMITH_BRAND_CONFIG` + `branding.brand()`, and resets the branding cache on
  both setup and teardown (mirroring `tests/conftest.py:37-50`'s
  `default_brand_resources`).

## 2. What happened before this report (context for the coordinator's reply)

My first pass hit `egf_local_dir()` returning `None` under the brief's exact fixture
and exact run command — `1 passed, 7 errors`. I stopped and reported NEEDS_CONTEXT
rather than guess at test-infrastructure changes affecting 7 more tasks. The
coordinator confirmed this was a defect in the plan (not my work), gave me the
`tests/plugins/cuo/conftest.py` shape to add (Option A), and the extra guard test.
That exchange is preserved in the conversation; this report covers what happened
after I received that guidance.

**One bug in the coordinator's given conftest snippet, fixed before use:** the given
code computed `_REPO = Path(__file__).resolve().parents[2]`. For a file at
`tests/plugins/cuo/conftest.py`, `parents[2]` is `tests/`, not the repo root —
`tests/conftest.py` uses `parents[1]` for the same reason (one directory shallower).
I changed it to `parents[3]`. Confirmed by direct probe:
```
$ .venv/bin/python -c "from pathlib import Path; p = Path('/Users/seriouscoderone/code/locksmith/tests/plugins/cuo/conftest.py'); [print(i, p.parents[i]) for i in range(4)]"
0 .../tests/plugins/cuo
1 .../tests/plugins
2 .../tests
3 .../locksmith          <- repo root
```
Without this fix, `sys.path` gained two nonexistent directories
(`tests/scripts`, `tests/packaging`) and `importlib.import_module("brandlib")`
raised `ModuleNotFoundError: No module named 'brandlib'` for every test in the file
(confirmed — this was the exact first failure after adding the conftest verbatim).

## 3. A second, more interesting bug: `order` was reading the wrong JSON field

After fixing the `parents[]` typo, the brand-activation fixture worked (confirmed by
the new guard test passing and `egf_local_dir()` resolving to
`.../release/usurance/egf`), but one test still failed:

```
FAILED tests/plugins/cuo/test_schema_source.py::test_order_is_the_declared_field_order_not_alphabetical
AssertionError: assert 'coverages' == 'line_of_business'
```

`schema.order` was `('coverages', 'jurisdiction', 'line_of_business', 'thesis',
'window_closes', 'window_opens')` — alphabetical, exactly what the test exists to
reject. This is not an infrastructure gap; the real bundled template really does have
its `properties` dict keys in alphabetical order:

```
$ python3 -c "... print(list(properties.keys()))"
['coverages', 'jurisdiction', 'line_of_business', 'thesis', 'window_closes', 'window_opens']
```

I checked whether this was a stale generated-bundle artifact by diffing the
gitignored `release/usurance/egf/<CUO-SAID>.json` against the committed source
`brands/usurance/egf/<CUO-SAID>.json` — byte-identical (`diff` produced no output,
same size, same mtime). So this is the real, committed, authoritative template
content, not a build artifact gone stale.

But the *same* JSON's `required` array is in the field order the test (and the
design) expects:

```json
"required": ["line_of_business", "jurisdiction", "coverages",
             "window_opens", "window_closes", "thesis"]
```

`properties` is alphabetized (an artifact of whatever tool wrote the template);
`required` carries the author's actual intended field order — the order a CUO would
naturally fill the form. The brief's given implementation built `order` by iterating
`properties.items()`, which is the wrong source for this bundle.

**Fix applied** (in `load_mandate_schema`): derive `order` from the schema's
`required` list (filtered to fields that actually exist), then append any property
*not* in `required` afterward in `properties` order — so a future optional field with
no declared position still appears exactly once, at the end, rather than being
dropped. `fields` itself is still built from `properties` (unaffected; dict lookup by
name doesn't care about source-dict order). Re-ran: `9 passed`. Ran twice more to
rule out fixture-teardown flakiness (cache not reset between runs): both clean.

I did not touch `brands/usurance/egf/` — the constraint "the EGF is READ-ONLY" stands;
this fix is entirely inside `schema_source.py`'s own parsing logic, reading a
different (already-present) key of the same JSON. No schema literal was added to
source to make this work — `"required"` is JSON-Schema vocabulary, not domain data,
same class of key name as `"properties"`, `"enum"`, `"pattern"` already read by the
brief's own code.

## 4. Why this is DONE_WITH_CONCERNS, not DONE

1. **Tasks 2/4/5/6 should know `properties` order ≠ declared order** in this bundle.
   If any later task reads `payload_schema["properties"]` directly (bypassing
   `MandateSchema.order`) expecting form-layout order, it will silently get
   alphabetical order instead. `load_mandate_schema().order` is now the correct
   source; anything that doesn't go through it is at risk.
2. **This may indicate the EGF template itself has a latent authoring inconsistency**
   worth fixing at the source someday (`brands/usurance/egf/<CUO-SAID>.json`'s
   `properties` block probably *should* be in `required`'s order too, so the two
   don't silently diverge for a future schema where not everything is required — my
   fallback-append logic is untested against that shape, since in the current bundle
   every property is required). I did not fix the template; I did not have
   authorization to, and "EGF is READ-ONLY" is a plan-wide constraint, not a Task-1
   one. Flagging for the plan owner's judgment, not fixing unilaterally.
3. Two deviations from "follow the brief literally": the `order`-derivation logic
   inside `load_mandate_schema`, and the `parents[3]` fix in the conftest the
   coordinator supplied. Both are documented above with the measurement that forced
   each one.

## 5. Full final verification

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
.........
9 passed in 0.06s
```
Ran a second time back-to-back (idempotency / cache-leak check): identical, `9 passed`.

No-schema-literal check (Global Constraint, re-verified after the `order` fix):
```
$ grep -n "workers_compensation\|US-\[A-Z\]\|\^\[A-Z0-9\]\[A-Z0-9-\]" src/locksmith/plugins/cuo/schema_source.py
(no output)
```

Commit:
```
$ git log -1 --stat
commit 9bdf0cfb52efebfcde89e500c23cfde9e04f5d56
    feat(cuo): read the mandate payload schema from the EGF
 src/locksmith/plugins/cuo/schema_source.py | 139 +++++++++++++++++++++++++++++
 tests/plugins/cuo/__init__.py              |   0
 tests/plugins/cuo/conftest.py              |  49 ++++++++++
 tests/plugins/cuo/test_schema_source.py    |  80 +++++++++++++++++
 4 files changed, 268 insertions(+)
```
Confirmed the staged/committed set was exactly these four files — the repo had
pre-existing unrelated uncommitted changes to `.superpowers/sdd/.gitignore`,
`docs/superpowers/plans/2026-08-08-cuo-mandate-form.md`, and a `brands/usurance/egf/
oobis/*.cesr` file from before this task started (not made by me); I used a scoped
`git add` on exactly the four intended paths rather than `git add -A`/`-a`, so none
of that pre-existing dirty state was swept into this commit.

## 6. Concerns for the reviewer

- Please double-check the `order` fix in §3 — it's the one place I deviated from the
  brief's literal implementation text based on my own read of the real data, rather
  than on instruction.
- The `required`-vs-`properties`-order divergence in the real EGF template (§4.2) is
  worth a decision from whoever owns `brands/usurance/egf/`: leave `properties`
  alphabetized (harmless as long as everything reads `.order`, not `properties`
  directly) or fix the template so the two agree.
- `tests/plugins/cuo/conftest.py` is now the shared brand-activation fixture for the
  whole `cuo` test package (autouse) — Tasks 2/4/5/6 should not duplicate it.

## 7. Fix report — review round 2

Review verdict: spec ✅, quality Approved, no Critical findings. Three items to
address before closing the task; all three are done.

### 7.1 (Important) Closed the untested `required=False` / append-fallback blind spot

The reviewer mutated `_constraints` to hardcode `required=True` unconditionally and
the suite stayed green — every field in the real bundled template happens to be
required, so that branch (and `order`'s append-fallback branch, for a property the
schema leaves out of `required`) was permanently unreachable testing only against the
shipped EGF.

Added `test_a_field_missing_from_required_is_optional_and_appended_last` to
`tests/plugins/cuo/test_schema_source.py` — a **synthetic** EGF built on `tmp_path`
(an egf-doc with one `micro_apps` entry, that template's `declare_product_mandate`
command, and a `payload_schema` whose `required` omits `beta`). Asserts:
- `schema.fields["beta"].required is False`
- `schema.order[-1] == "beta"` (the append-fallback branch)
- (plus `alpha`/`gamma` are `required is True` and occupy `order[:2]` in `required`'s
  order, so the test also still checks the happy path it's sitting next to)

Documented in both the test module's docstring and the new test's own docstring why
this one test uses a synthetic fixture when the file's opening docstring says real-
bundle-only: the real bundle cannot express "a field missing from `required`" because
every field in it *is* required, so a synthetic case is the only way to reach the
branch at all. Every other test in the file is still against the real bundle.

**Verified the fix actually closes the gap**, not just that the new test passes:
reproduced the reviewer's exact mutation (hardcoded `required=True` in `_constraints`),
confirmed the new test fails against it —
```
FAILED tests/plugins/cuo/test_schema_source.py::test_a_field_missing_from_required_is_optional_and_appended_last
AssertionError: assert True is False
```
— then reverted the mutation and confirmed `10 passed` again.

### 7.2 (Minor) `_cuo_template` now raises `SchemaSourceError` on a corrupted template

Was: `return json.loads(path.read_text(encoding="utf-8"))` with no guard — a
corrupted `<said>.json` raised a raw `json.JSONDecodeError`, breaking the module's
one-error-type promise. Checked `_egf_doc` for the same hole: it already wraps its
own `json.loads` in `try/except (OSError, ValueError): continue` and raises
`SchemaSourceError` once no candidate file matches, so it did not need the fix.

Now:
```python
try:
    return json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError) as exc:
    raise SchemaSourceError(f"{path} is not valid JSON: {exc}") from exc
```
Verified directly (not just by absence of a failure): built a temp EGF dir with a
valid egf-doc and a `<said>.json` containing `"{not valid json"`, called
`load_mandate_schema`, confirmed `SchemaSourceError` is raised (not
`JSONDecodeError`) and its message contains the offending path:
```
SchemaSourceError raised, as required: /.../ECORRUPTTEMPLATE....json is not valid JSON: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
```

### 7.3 (Design decision) `order` documentation no longer overclaims

Per the coordinator: presentation order is moving to `mandate_copy.FIELD_ORDER`
(Task 3's authority, used for both form layout and the order validation reports
errors in) — I do not implement it here, Task 3 owns it.

What I own: rewrote the docstrings so `MandateSchema.order` and `load_mandate_schema`
stop claiming `required`'s order is authoritative. Added a docstring to the
`MandateSchema` dataclass itself (it had none before) stating plainly that `order` is
"a best-effort reading... a canary, not an authority," that `required` is a
JSON-Schema *set* with nothing distinguishing authored order from incidental
alphabetical order, and that `mandate_copy.FIELD_ORDER` (Task 3) is the single
authority for field sequence. Updated `load_mandate_schema`'s docstring to match:
kept the alphabetized-`properties` measurement (the valuable, verified-against-the-
real-bundle observation), added the explicit admission that this "only relocates the
fragility... it does not remove it," and pointed at `FIELD_ORDER` as where
presentation order will actually live.

Left `test_order_is_the_declared_field_order_not_alphabetical` in place, unchanged —
per instruction, it stays as a canary against the real bundle and will fire the day
`required` gets alphabetized too.

### 7.4 Final verification

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
..........
10 passed in 0.09s
```

No-schema-literal check (re-verified, unaffected by these changes):
```
$ grep -n "workers_compensation\|US-\[A-Z\]\|\^\[A-Z0-9\]\[A-Z0-9-\]" src/locksmith/plugins/cuo/schema_source.py
(no output)
```

### 7.5 Commit

Only `src/locksmith/plugins/cuo/schema_source.py` and
`tests/plugins/cuo/test_schema_source.py` changed in this round (no new files); both
staged explicitly and committed together. The repo's pre-existing unrelated dirty
files (`.superpowers/sdd/.gitignore`, `docs/superpowers/plans/2026-08-08-cuo-mandate-
form.md`, a `brands/usurance/egf/oobis/*.cesr`) remain untouched by this commit, same
as round 1.

### 7.6 Two Minor findings acknowledged, not changed (per coordinator)

Recorded here for completeness, not acted on: the module docstring's forward
reference to `tests/plugins/cuo/test_no_schema_literals.py` (Task 7 creates it — the
forward reference is correct as written), and the conftest's unrolled-back path if
`branding.brand()` itself raises after `load_brand()` already mutated the global
(low probability, self-heals for the next test in the package — no machinery added).
