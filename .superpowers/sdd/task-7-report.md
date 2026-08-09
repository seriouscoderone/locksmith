# Task 7 report: the two generator-level guards

Commit: `962960259400d784d25f28421762488328b27e96`
Branch: `claude/cuo-mandate-form`

## What was implemented

Two new test files, both generator-level guards (fail on a defect *class*, not a
behaviour that currently exists):

- `tests/plugins/cuo/test_no_schema_literals.py`
- `tests/plugins/cuo/test_schema_copies_agree.py`

Plus a docstring correction in `src/locksmith/plugins/cuo/page.py` (see below).

### Guard 1 — corrected, not transcribed

The brief's Step 1 code for `test_no_schema_literals.py` was flagged as wrong: a
literal substring scan (`value in text`) false-positives on ordinary English --
`"life"` is a substring of the word "lifecycle", `"property"` is a substring of
the word "properties", both of which are legitimate prose already present in this
package (`page.py`'s `# -- lifecycle --` section heading, `schema_source.py`'s
"this bundle's `properties` block" comment).

I measured this empirically rather than taking it on faith. I copied the brief's
exact Step-1 code into a scratch test file and ran it against the current tree:
it actually **passed**, because the enum-member test in the brief already
requires the value to be wrapped in matching quote characters
(`f'"{v}"' in text or f"'{v}'" in text`), which incidentally rules out the
"lifecycle"/"properties" substring problem for that specific check (a quote
mark never appears mid-word). So the concrete failure mode described in the task
is real for a *naive* substring scan, but the brief's own quote-guarded version
happened to dodge it by luck, not by design -- it doesn't generalize (e.g. a
regex-literal check done the same naive way, or a future schema value that isn't
a plain lowercase word, could still trip it), and it doesn't do the second half
of what's needed either: excluding prose from the picture on principle rather
than by accident of the quote characters lining up.

**Design implemented** (two independent checks, applied to every source file
under `src/locksmith/plugins/cuo/`, for every enum member and both regex
literals):

1. **`_quoted_hits`** -- STRICT. Scans the raw, unmodified file text (comments and
   docstrings included) for the literal wrapped in matching quote characters
   (`"value"` or `'value'`). A schema value restated in a comment, quoted the way
   Python would quote it, is still a restatement of the schema and still a drift
   risk the day the enum changes -- so comments are IN SCOPE here.
2. **`_bare_word_hits`** -- word-bounded (`\b`-delimited, so "lifecycle" can never
   match "life"), scanned only against a version of the source with every
   COMMENT and STRING token blanked out via Python's `tokenize` module. Comments
   and docstrings are OUT OF SCOPE here on purpose: an ordinary English word in
   prose is not a restatement of anything, and this check exists only to catch
   the rarer case of a schema value reaching source *unquoted*, as a bare token
   in code that actually runs.

Every offender is reported as `{filename: which check fired}` (or, for the enum
test, `{filename: {value: which check fired}}`), so a failure names the file,
the exact literal, and whether it was a quoted restatement or a bare-code
occurrence -- actionable without re-deriving the scan.

I validated this design against the real source tree with a standalone script
before writing the test file (see "Resolution" below) and confirmed all four
cases behave as intended: a bare word in real code is caught, a word inside a
comment is not, a substring inside a longer word in a comment is not, and a
substring inside a longer bare word in code is not.

### Guard 2 — implemented as specified

`test_schema_copies_agree.py` matches the brief's Step 1 code as given (it had no
defect flagged). It reconciles `schema_source.load_mandate_schema`'s
`payload_schema` reading against the ACDC schema's attribute block, located by
`credentialType == "UsuranceProductMandate"` -- verified present in the bundle at
`brands/usurance/egf/EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5.json` (confirmed
by scanning every `E*.json` in the bundle and printing each one's
`credentialType`; that file is the only one carrying
`"UsuranceProductMandate"`, and it matches the `PRODUCT_MANDATE_SCHEMA_SAID` pin
already in `page.py`).

### page.py docstring correction

The module docstring's claim -- "`test_no_schema_literals.py` (Task 7, not yet
written) enforces that by grepping this package for schema values; it reads
whole files, so a schema value is banned from a COMMENT here too, not only from
code" -- was stale in two ways: the file now exists, and the "reads whole files"
claim was only half true under the corrected design (true for the quoted-literal
check, false for the bare-word check, which explicitly excludes comments).
Rewrote it to describe the actual two-check design, citing the two real
whole-word prose occurrences already in this package (`review_dialog.py`'s "for
the life of", `schema_source.py`'s "any property the schema") as the concrete
reason bare prose is out of scope. Also had to route around a bootstrapping trap
of my own making: my first draft of that paragraph wrote out
`"workers_compensation"` with matching quote marks as an example, and the guard
correctly failed on it -- a quoted literal in a docstring being flagged is
exactly what the strict check is supposed to do, and the docstring was the
defect, not the guard. Reworded to describe the example without constructing a
matching quoted literal.

## Test command and full output

Exactly as specified:

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_no_schema_literals.py tests/plugins/cuo/test_schema_copies_agree.py -q --import-mode=importlib
```

```
......                                                                   [100%]
6 passed in 0.12s
```

Full package regression (not the whole suite, per instructions -- scoped to
`tests/plugins/cuo/`):

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
```

```
........................................................................ [ 50%]
.......................................................................  [100%]
143 passed, 1 warning in 3.28s
```

143 = 137 pre-existing + 6 new. None of the 137 broke. (The one warning is a
pre-existing `pysodium` `DeprecationWarning`, unrelated to this change.)

## Both guards observed failing, then passing

### Guard 1 -- pasting an enum value into source

Before:

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_no_schema_literals.py -q --import-mode=importlib
....                                                                     [100%]
4 passed in 0.11s
```

Inject:

```
printf '\n_TEMP = "workers_compensation"\n' >> src/locksmith/plugins/cuo/mandate_copy.py
```

After:

```
...F                                                                     [100%]
=================================== FAILURES ===================================
____________________ test_no_enum_member_appears_in_source _____________________
...
E       AssertionError: {'mandate_copy.py': {'workers_compensation': 'quoted string literal (comments and docstrings included)'}} hardcode line_of_business values; build the dropdown from the schema's enum
E       assert not {'mandate_copy.py': {'workers_compensation': 'quoted string literal (comments and docstrings included)'}}

tests/plugins/cuo/test_no_schema_literals.py:156: AssertionError
1 failed, 3 passed in 0.12s
```

Names the file (`mandate_copy.py`), the exact literal (`workers_compensation`),
and which check fired (the quoted-literal check). Reverted with
`git checkout -- src/locksmith/plugins/cuo/mandate_copy.py`; re-ran, back to 4
passed.

### Guard 2 -- corrupting the minItems comparison

Before:

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_schema_copies_agree.py -q --import-mode=importlib
..                                                                       [100%]
2 passed in 0.03s
```

Inject: changed `assert a.get("minItems") == f.min_items, name` to
`assert a.get("minItems", 99) == f.min_items, name`.

After:

```
F.                                                                       [100%]
=================================== FAILURES ===================================
_______________ test_every_payload_field_matches_the_acdc_schema _______________
...
>           assert a.get("minItems", 99) == f.min_items, name
E           AssertionError: line_of_business
E           assert 99 == None
1 failed, 1 passed in 0.04s
```

Fails on `line_of_business` (the first field in `payload.order` that has no
`minItems` in either schema, so the default of 99 masks nothing and mismatches
`None` immediately) -- confirms the comparison is load-bearing, not a no-op.
Reverted by hand (this file was untracked at the time, so `git checkout --`
correctly refused with "did not match any file(s) known to git"; fixed with an
Edit instead). Re-ran, back to 2 passed.

## How I resolved the substring-vs-word-boundary question, and why

Two independent axes, not one combined rule:

1. **Scope** -- where is the guard allowed to look? Comments and docstrings, or
   code only?
2. **Shape** -- what counts as a match? A quoted string literal, or any
   whole-word occurrence?

The owner's stated view in the task (which I adopted after checking it against
the actual occurrences in this package) pairs these two axes deliberately rather
than crossing them uniformly:

- **Quoted + everywhere.** A schema value written the way Python writes a string
  literal (`"workers_compensation"`) is a restatement of the schema regardless of
  whether the interpreter ever executes that line. A commented-out
  `# valid_values = ["property", ...]` is exactly the kind of thing that goes
  stale the day the EGF's enum changes and nobody notices, because nothing
  imports it. So this check is strict, and it reads the whole file.
- **Bare word + code only.** A bare, unquoted occurrence of the same word is only
  interesting if it is something the interpreter actually runs -- an identifier,
  a bare name, some other token-level artifact. In prose (a comment or
  docstring), the same word is almost certainly just English: `schema_source.py`
  legitimately says "any property the schema leaves out of `required`", and
  `review_dialog.py` legitimately says "for the life of". Flagging those would
  make the guard fail on correct code, which is precisely the failure mode this
  task was assigned to fix. So this check excludes comments and docstrings, and
  requires a whole-word boundary so "lifecycle" can never match "life" in the
  first place (belt-and-suspenders with the scope restriction, not a substitute
  for it).

I did not implement a third variant (quoted-but-code-only, or
bare-word-but-everywhere) because neither pairing matches a real defect
mode I could name: a quoted literal in code is already caught by the
comments-included quoted check (a superset), and a bare word in comments is
exactly the false-positive case being fixed, not a defect to catch.

I verified the design against the actual package contents (not just against
synthetic examples) before trusting it: a script scanning every enum member and
both regex literals against every file in `src/locksmith/plugins/cuo/` found
zero hits under either check on the unmodified tree, and I confirmed by hand
that the four cases that matter -- bare word in real code, word inside a
comment, substring inside a longer word in a comment, substring inside a longer
bare word in code -- each resolve the way the design intends (first case
flags, other three don't).

## Concerns for the reviewer

- `_code_only`'s comment/string-blanking uses Python's `tokenize` module and
  raises on anything it cannot tokenize. Every file under
  `src/locksmith/plugins/cuo/` tokenizes cleanly today (confirmed by running the
  guard), so this has not been exercised in its failure path. If it ever raises
  in CI, that is the guard correctly refusing to vouch for a file it cannot
  parse -- not a bug to silence.
- The bare-word check has no real defect case backing it in this codebase today
  (no schema value has ever appeared unquoted in source, quoted or not) --  it
  exists because the task asked for whole-word matching as a named requirement,
  and because it is the check that would catch a value pasted in some form the
  quoted check's exact-quote-match wouldn't recognize (e.g. inside an f-string
  built from concatenated fragments). I could not construct a realistic scenario
  where it fires and the quoted check doesn't, given how the enum values are
  actually used in this package (always as complete dropdown/string values, never
  assembled). Its main proven value today is that it does NOT false-positive
  on the two real prose occurrences already in the tree -- worth keeping an eye
  on if it ever needs to be simplified away.
- I did not re-verify the regex-literal checks' discrimination directly (Step 3
  of the brief only asked for the enum-member case and the agreement guard); the
  same `_offenders` helper backs both `test_no_schema_regex_appears_in_source`
  and `test_no_enum_member_appears_in_source`, so the enum-member proof exercises
  the same code path, but a reviewer who wants the regex case proven explicitly
  can paste `_TEMP = "^US-[A-Z]{2}$"` into any file under
  `src/locksmith/plugins/cuo/` and expect the same failure shape.
- I left `.superpowers/sdd/.gitignore`, `brands/usurance/egf/oobis/...cesr`, and
  `docs/superpowers/plans/2026-08-08-cuo-mandate-form.md` unstaged/uncommitted --
  they were already modified in the working tree before I started this task and
  are not part of Task 7's scope.
