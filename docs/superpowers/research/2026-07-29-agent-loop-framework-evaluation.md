# Agent-loop framework evaluation — embedded assistant (Locksmith)

Date: 2026-07-29. Scope: build-vs-borrow decision for the embedded assistant described in
`docs/superpowers/specs/2026-07-29-embedded-assistant-keri-native-design.md` and
`docs/superpowers/plans/2026-07-29-embedded-assistant-library-phase01-plan.md` (KERI wallet,
local `llama-server` sidecar, hard constrained decoding, plan-then-execute with one
crypto-signing checkpoint, runtime tool manifest). This document cites URLs for every
version-specific claim and flags anything that could not be verified live.

---

## 0. The one fact everything else hangs on: what llama-server actually does

This is foundational because every framework's "constrained decoding" score depends on
whether it can reach this mechanism, not reimplement it.

- `llama-server`'s native `/completion` endpoint accepts a `grammar` field (raw GBNF) and a
  `json_schema` field (JSON-Schema, server-converted to GBNF) — both documented, both
  confirmed working, no known open bugs.
  [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- The OpenAI-compatible `/v1/chat/completions` endpoint accepts `response_format: {type:
  "json_schema"|"json_object", ...}` which the server converts to a grammar server-side —
  this is the exact "post JSON-Schema, server compiles to GBNF, masks logits" mechanism the
  spec assumes. **Verified as a genuine hard guarantee**: llama.cpp's grammar sampler zeroes
  the probability of any token that would violate the grammar, so non-conforming output is
  structurally impossible, not just discouraged — this is the same mechanism whether you hit
  it through `/v1/chat/completions` or `/completion`.
- **Caveat, verified via GitHub issue history, not still-open but worth re-testing on your
  pinned build**: [ggml-org/llama.cpp#11847](https://github.com/ggml-org/llama.cpp/issues/11847)
  documented that `response_format` on `/v1/chat/completions` broke specifically when the
  server was started with `--jinja` (needed for tool-calling chat templates) — it errored
  "Either json_schema or grammar can be specified, but not both." Root cause was in the
  `--jinja` request-parsing path; fixed by [PR #11900](https://github.com/ggml-org/llama.cpp/pull/11900),
  merged into build b4739 (2025-02-19) — over a year before this evaluation, so current
  llama.cpp should be clean, but a commenter on 2025-02-20 still reported `response_format`
  with `json_schema` returning unformatted text in some case right after the fix landed.
  **Recommendation regardless of framework choice**: treat `/completion`'s native `grammar`/
  `json_schema` fields as the primary, most-trustworthy integration point (it never had this
  bug), and if you use the OpenAI-compatible `/v1/chat/completions` route (which most
  frameworks assume), smoke-test `response_format` + `--jinja` + tool-calling together on
  your exact pinned llama.cpp commit before relying on it.
- `oneOf` and `const`/`enum` are both supported by llama.cpp's JSON-Schema→GBNF converter
  (union rules for `oneOf`, constant rules for `const`/`enum`) —
  [json_schema_to_grammar.py](https://github.com/ggml-org/llama.cpp/blob/master/examples/json_schema_to_grammar.py),
  [grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md).
- **Real perf gotcha for "dynamically computed enum" (constraint #5)**: llama.cpp's grammar
  engine has to iterate the vocabulary and update parser-stack state per candidate token;
  large/complex grammars (e.g. an `enum` with hundreds of session-valid identifier strings)
  are a documented source of slow sampling, distinct from the "x? x? x?..." repetition
  antipattern also called out in the grammar docs
  ([grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)).
  **Mitigation that exists today**: llama.cpp has an opt-in **LLGuidance** backend
  (`-DLLAMA_LLGUIDANCE=ON` at build time; requires adding a Rust/cargo toolchain to the build)
  that intercepts JSON-Schema requests automatically once compiled in and is reported as
  "very fast, excellent JSON-Schema coverage"
  ([docs/llguidance.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/llguidance.md)).
  If your session-valid identifier/schema-hash enums get large, budget time to evaluate this
  build flag rather than assuming default GBNF will stay fast — this is independent of
  whichever agent framework you pick.
- **Model-capability caveat, not a framework issue**: grammar constraint guarantees the
  *shape* of the output (valid JSON matching schema, value drawn from the allowed enum) — it
  does **not** guarantee the model picks the *semantically correct* tool or enum member.
  General 2026 benchmarking commentary is skeptical of sub-8B models' native tool-calling
  reliability even with structured decoding aids ("gemma4:2b... still is not
  production-ready for a real agent" — [promptquorum.com](https://www.promptquorum.com/power-local-llm/best-local-models-tool-calling-2026),
  general local-LLM tool-calling roundups, mid-2026). Qwen3 4B Q4_K_M is a small model; the
  hard grammar constraint should be treated as "never crashes / never produces unparseable
  output," not "always picks the right action." This reinforces why the design already wants
  a human-approved plan step and a re-ask-on-divergence loop — that safety net is doing real
  work regardless of framework choice.
- **Bigger, sharper version of that same caveat — "constraint tax" / tool suppression, verified
  against a specific, dated paper**: Li, Zhang & Lv, ["Constraint Tax in Open-Weight LLMs: An
  Empirical Study of Tool Calling Suppression Under Structured Output Constraints"](https://arxiv.org/abs/2606.25605)
  (submitted 2026-06-24, i.e. about five weeks before this evaluation). Their finding is more
  specific and more actionable than generic small-model skepticism: when tool-calling and a
  JSON-schema/grammar constraint operate **simultaneously in one decoding pass**, open-weight
  models can enter a **"Tool Suppression"** mode — schema compliance stays high, but the model
  stops invoking tools at all, because grammar-based token masking renders the tool-call tokens
  themselves unreachable at the point the model would otherwise choose to call a tool (their
  "Constraint Priority Inversion" hypothesis: schema satisfaction ends up dominating
  action-selection). Their proposed fix, **"Transparent Two-Pass Execution,"** separates the
  *decision of which action to take* from *the constrained generation of that action's
  arguments* — i.e., don't ask one grammar-constrained call to simultaneously decide "should I
  act, and if so how" AND "produce perfectly-shaped arguments." **This is directly actionable
  for this project's exact architecture**: structure each turn as (1) an unconstrained or
  lightly-constrained "decide the next step" pass, then (2) a separate, fully hard-constrained
  pass that only fills in that one step's arguments against the dynamic enum/schema. This is a
  prompt/call-shape decision that sits above any framework choice — worth building into the loop
  design regardless of which option below is chosen, and worth explicit test coverage before
  trusting the checkpoint-approval flow on a 4B model.

---

## 1. Reading order

Sections 2–10 give per-option detail; §11 has the full side-by-side comparison table; the
**Bottom line** at the end has the recommendation. Section 0 above (llama-server's actual
mechanism, and two evidence-based risk findings — grammar performance on large enums, and
"constraint tax"/tool suppression under simultaneous constraint+tool-calling) applies to every
option below and is worth reading first, since it's what most of the per-framework "constrained
decoding" verdicts are measured against.

---

## 2. Hand-rolled loop (the baseline)

A hand-rolled loop here means: `httpx` client → `llama-server` (`/completion` or `/v1/chat/completions`),
a small amount of glue code to (a) build a JSON-Schema per call from the current session's dynamic
allowlist (`pydantic.create_model` or a raw `dict`), (b) POST it, (c) parse the guaranteed-valid JSON
back, (d) look up the named tool in a runtime registry (a `dict[str, ToolTemplate]` built from the
loaded JSON templates — no decorators, no import-time binding at all, because there's no framework
imposing a registration API), (e) execute it, (f) on divergence from the approved plan, stop and
re-prompt for approval.

- **HITL**: trivial and exactly bespoke to spec, because you write it: the "propose plan" step is
  just one more schema-constrained call whose *entire output* is the plan (a list of steps with
  their args, matching a `Plan` JSON-Schema); the code computes `sha256(canonical_json(plan))`,
  shows it and a rendering of the plan to the human, and — critically — **that hash is what actually
  gets signed** at the one cryptographic checkpoint. No framework in this survey has a primitive for
  "the approval is a detached signature over a content hash of the approved artifact" — that's an
  application-level, KERI-native concern (the signing ceremony should go through the same signing
  path as any other KERI event, per this repo's BE-KERI-NATIVE law, not a bolted-on generic
  signature scheme) and every option in this document, framework or hand-rolled, requires writing it
  yourself. The hand-rolled loop doesn't have to fight a framework's own checkpointer/interrupt
  semantics to get this right — a real advantage when the whole point is "this one gate must be
  literally unbypassable," not "unbypassable modulo the framework's resume plumbing."
- **Local/offline**: as native as it gets — you pick the endpoint (`/completion` is the one with zero
  known `response_format` history; `/v1/chat/completions` is the one every framework assumes).
- **Constrained decoding**: full raw pass-through by construction — there is no library between you
  and the `grammar`/`json_schema` field, and no framework machinery layering a soft validate-and-retry
  on top by default (you can add pydantic validation as defense-in-depth, but it isn't required to
  get correctness — the server already guarantees it).
- **Dynamic tools**: trivially runtime — your "tool manifest" is just the JSON templates, loaded once
  per session, mapped into whatever internal shape you want. Nothing to fight.
- **Dependency weight**: as light as `httpx` + `pydantic` (already a Locksmith dependency family
  concern to check, but both are small, pure/near-pure-Python, and freeze cleanly with PyInstaller —
  no dynamic entry-point discovery, no plugin metadata scanning of the kind that bites `langchain`/
  `strands` style frameworks) + `jsonschema` if you want client-side defense-in-depth validation too.
- **Planning**: you write the "propose whole plan as one schema-constrained call, hash it, gate
  execution on a signed hash, then deterministically walk the approved steps" state machine yourself.
  This is maybe 150–300 lines of code, not a research problem — every framework surveyed here would
  need nearly the same amount of custom code bolted on for the parts that are actually novel
  (plan-hash-binding, the crypto checkpoint), so "we didn't have to learn a framework's opinions about
  state/graphs/sessions to get there" is a genuine, not merely lazy, advantage.
- **Verdict: Good fit.** The specific unusual combination of requirements here (subprocess sidecar
  only, hard grammar constraint as the *primary* correctness mechanism rather than a nice-to-have,
  runtime-templated tools, and a bespoke sign-the-plan-hash checkpoint) is small enough in surface
  area, and different enough from what any of the surveyed frameworks optimize for, that the
  framework's value-add (orchestration, retries, multi-agent patterns, provider abstraction) is mostly
  either irrelevant (we only ever have one provider: our own pinned llama-server) or actively in the
  way (frameworks want to own the loop and the resume semantics; we need to own the one checkpoint
  ourselves for it to be trustworthy).

## 3. Strands Agents (AWS, open source) — detail

Not in the original candidate list but surfaced during research as a strong match; **not one of the
frameworks named by the user, flagging that explicitly**. Apache-2.0, maintained by AWS
(`author: AWS <opensource@amazon.com>`), current release **1.50.2** as of **2026-07-27** (two days
before this evaluation), commit activity described as active/frequent.
[pypi.org/project/strands-agents](https://pypi.org/project/strands-agents/),
[github.com/strands-agents/harness-sdk](https://github.com/strands-agents/harness-sdk).

- **HITL**: First-class and, per the docs, **structurally enforced**: the agent loop's own control
  flow checks `if result.stop_reason != "interrupt": break`, i.e. the loop cannot advance past a
  raised interrupt without an explicit resume call — this is not a callback convention that careless
  code could skip.
  [Interrupts docs](https://strandsagents.com/docs/user-guide/concepts/interrupts/),
  [Human-in-the-Loop docs](https://strandsagents.com/docs/user-guide/concepts/agents/interventions/human-in-the-loop/).
  State persists via `FileSessionManager`, so a pause can survive a process/app restart, not just an
  in-memory pause — useful given this is a desktop app that could be closed mid-approval.
  **Gap versus our spec**: interrupts are wired at `BeforeToolCallEvent`, i.e. natively **per-tool-call**,
  not "pause once for the whole plan." Every example found gates a single sensitive tool call (e.g.
  `delete_files`), not a multi-step plan reviewed as one unit. To get single-approval-for-the-whole-plan
  you'd use the same trick as the hand-rolled loop: make "propose the plan" itself the one tool call
  that's gated, then execute the approved steps deterministically outside further LLM discretion (or
  with the LLM only filling in already-approved step args). This is buildable on Strands' primitives,
  but it is not the primitive Strands ships out of the box — the docs show no ready-made "approve this
  whole plan" pattern.
- **Local/offline**: dedicated `strands.models.llamacpp.LlamaCppModel` provider, confirmed via docs to
  connect over **HTTP to a separate `llama-server` process** (`base_url="http://localhost:8080"`,
  default), not in-process bindings — directly matches the subprocess-sidecar/crash-isolation
  requirement. [strands.models.llamacpp docs](https://strandsagents.com/docs/api/python/strands.models.llamacpp/).
  Notably this provider is **not gated behind a PyPI extra** (no `llamacpp` entry in `requires_dist`) —
  it rides on the core `httpx` dependency, so no extra install surface.
- **Constrained decoding**: the same provider exposes `grammar` (raw GBNF) and `json_schema` params
  that are, per the docs, passed **raw to the server** — i.e. the hard sampler-level guarantee, not a
  client-side validate-and-retry. `structured_output(output_model: type[T], ...)` accepts the schema
  per call, so dynamically-computed schemas/enums are supported (build a fresh Pydantic model or raw
  schema dict per call, same as the hand-rolled approach).
- **Dynamic/runtime tool registration**: genuinely runtime-capable, not merely decorator-bound. Tools
  can be plain modules exposing a `TOOL_SPEC` dict (`{"name", "description", "inputSchema": {"json":
  <schema>}}`) plus a matching function — no decorator required — and the `ToolRegistry` additionally
  supports `register_tool()` for registering tools built entirely from data at runtime, and can ingest
  file paths, import paths, imported modules, decorated functions, or `AgentTool` instances
  interchangeably.
  [strands.tools.registry docs](https://strandsagents.com/docs/api/python/strands.tools.registry/),
  [Dynamic Tool Loading in Strands SDK](https://builder.aws.com/content/2zeKrP0DJJLqC0Q9jp842IPxLMm/dynamic-tool-loading-in-strands-sdk-enabling-meta-tooling-for-adaptive-ai-agents).
  This is the best match found for "tool manifest derived at runtime from declarative JSON templates."
- **Dependency weight — the real wart**: verified directly from PyPI metadata (`pip download`
  metadata / `requires_dist`), the **unconditional, non-optional** core dependencies are:
  `boto3`, `botocore`, `docstring-parser`, `httpx`, `jsonschema`, `mcp` (Model Context Protocol SDK),
  `opentelemetry-api`, `opentelemetry-instrumentation-threading`, `opentelemetry-sdk`, `pydantic`,
  `pyyaml`, `typing-extensions`, `watchdog`. `boto3`/`botocore` in particular are pulled in **even
  though this deployment never touches AWS/Bedrock** — `botocore` alone is a large, non-trivial
  package (embedded service JSON definitions) and is a real PyInstaller size/scan-time cost with no
  functional payoff here. The `mcp` SDK and three `opentelemetry-*` packages add further weight and
  transitive surface for a fully-offline desktop app that needs none of it.
  **Could not verify**: no PyInstaller-specific freezing issues/hooks for `strands-agents` were found
  in a targeted search (no GitHub issues, no hook package) — this is genuinely unverified, not
  confirmed-clean; budget a real freeze-and-smoke-test spike before committing, same as for any
  candidate.
  Side note relevant to this repo's BE-KERI-NATIVE law: Strands also ships an optional `cedar` extra
  (`cedarpy`, AWS's Cedar policy language) for tool-authorization policies — a generic expression
  language, which per this repo's law would only be acceptable for **non-KERI app-logic** gating
  (e.g., "can this session invoke the CSV-transform tool at all"), never as a substitute for
  credential/KEL-based authority over the one signing checkpoint. Not evaluated further since it's
  optional and unnecessary for our use.
- **Planning**: ships `Graph`/`Workflow` multi-agent orchestration patterns (deterministic
  node/edge pipelines, dependency-resolved parallel task execution via the `strands-agents-tools`
  `workflow` tool) — closer to a DAG-of-agents primitive than a single "plan, review, execute" state
  machine. Usable as scaffolding, but the single-approval-on-one-plan-artifact behavior is still
  something we assemble ourselves on top, same as with LangGraph.
- **Verdict: Good fit, best borrow candidate found, dependency weight is the real cost.** It is the
  only surveyed framework with a purpose-built, HTTP (not in-process) llama.cpp provider that passes
  raw grammar/json_schema through, combined with structurally-enforced interrupts and genuinely
  data-driven runtime tool registration — three separate "good fit" boxes that no other framework in
  this survey ticks simultaneously. The cost is dragging in `boto3`/`botocore`/`opentelemetry`/`mcp`
  unconditionally for a fully offline app that uses none of them, which cuts against the "dependency
  weight and transitive-dep risk matter" constraint. If the team is willing to pay that freeze-size/
  audit cost for the fit on the other five axes, it's worth a hands-on PyInstaller spike; if not, the
  hand-rolled loop gets you the same three "good fit" boxes with none of the extra weight, at the
  cost of writing your own (small) loop.

## 4. Constrained-decoding-first options: Outlines, XGrammar, llama-cpp-agent

The premise of this survey slot was "maybe skip the agent framework, take a decoding-constraint
library and hand-roll the loop around it." Verified finding: **for this project's exact
architecture (llama-server as an out-of-process HTTP sidecar), none of these three add anything —
llama-server already does the hard constraining itself, server-side.**

- **Outlines** ([dottxt-ai/outlines](https://github.com/dottxt-ai/outlines), latest release
  **1.3.2**, published **2026-07-20** — nine days before this evaluation, actively maintained).
  Its llama.cpp integration is **in-process only**: the documented setup instantiates a
  `llama_cpp.Llama(...)` object directly (`from llama_cpp import Llama; llm =
  Llama("./phi-2.Q4_K_M.gguf")`) via the `llama-cpp-python` bindings — there is no documented
  remote-server mode for this backend.
  [Llama.cpp — Outlines docs](https://dottxt-ai.github.io/outlines/reference/models/llamacpp/).
  A **2022–2025-era open GitHub issue asking for exactly this** —
  [dottxt-ai/outlines#513, "Support for llama.cpp remote server"](https://github.com/outlines-dev/outlines/issues/513) —
  confirms this is a known, requested-but-unimplemented gap, not an oversight in the docs.
  **This is a disqualifier for our use case**: Outlines needs in-process access to logits, which
  is exactly what the subprocess-sidecar/crash-isolation requirement rules out. (Outlines does
  support remote HTTP backends for *other* engines — SGLang, vLLM, TGI — just not llama.cpp.)
- **XGrammar**: the grammar-compilation library behind constrained decoding in vLLM/SGLang/MLC.
  Targeted searching turned up **no evidence that llama.cpp has adopted XGrammar** as a decoding
  backend — llama.cpp's own docs and grammar tooling reference only its native GBNF engine and,
  optionally, **LLGuidance** as an alternate backend (see §0) — not XGrammar. **Could not find a
  llama.cpp/XGrammar integration PR or issue at all**, positive or negative; treating this as "not
  integrated" on absence of evidence after a real search, not confirmed non-existence. Either way,
  XGrammar is a library you'd embed in your own inference server, not something you point at an
  existing `llama-server` process — not applicable to this architecture regardless.
- **llama-cpp-agent** ([Maximilian-Winter/llama-cpp-agent](https://github.com/Maximilian-Winter/llama-cpp-agent)):
  the one option in this whole survey purpose-built around llama.cpp grammar/structured-output
  tool calling. Verified via the GitHub API: last push **2026-03-09** (~4.5 months before this
  evaluation — not abandoned), but **25 open issues** and the **latest tagged release is 0.2.35
  from 2024-06-29** — over two years stale relative to `master`, meaning whatever's shipped to
  PyPI is well behind what's in the repo. Its own README describes it as built for direct
  interaction via `llama-cpp-python`-style bindings (in-process), not an HTTP client to a
  standalone `llama-server`; this project predates the model-provider pattern seen in
  Strands/Strands-style HTTP clients and was not confirmed to support a remote-server mode.
  **Verdict: poor fit** — stale release cadence for a niche one-person project plus no confirmed
  HTTP-sidecar mode is too much risk to take a dependency on for a shipped desktop product,
  regardless of how well-targeted its structured-output feature set is conceptually.
- **Bottom line for this whole category**: the "decoding-constraint library" premise assumes you
  need one *because your inference runtime doesn't already constrain for you*. Ours does — that's
  the whole reason the design already specifies posting JSON-Schema straight to `llama-server`.
  Outlines/XGrammar solve a problem this architecture doesn't have (they're for when your engine
  is `transformers`/raw PyTorch and needs an outside library to get logit masking at all).
  llama-cpp-agent solves the right problem but is too thin/stale to bet a shipped product on.

## 5. LangGraph

- **HITL**: `interrupt()` raises a `GraphInterrupt` inside a node, halting execution and surfacing
  a value to the caller; resume is `Command(resume=<value>)`, which the docs describe as
  re-entering and re-executing the node from its start
  ([interrupt reference](https://reference.langchain.com/python/langgraph/types/interrupt),
  [Human-in-the-Loop and Interrupts](https://deepwiki.com/langchain-ai/langgraph/3.7-human-in-the-loop-and-interrupts)).
  This **requires a checkpointer** — `MemorySaver` for in-process-only persistence, or
  `SqliteSaver`/`PostgresSaver` for durable, cross-restart persistence — matching the desktop
  app's "survive a restart mid-approval" need if a durable checkpointer backend is wired in.
  Structurally enforced in the same sense as Strands: the interrupt is a control-flow exception,
  not a callback convention. **Gating a whole plan rather than per-tool-call is achievable, and is
  closer to LangGraph's native idiom than any other framework surveyed**: because a LangGraph graph
  is an arbitrary node/edge DAG you define yourself, the natural pattern is a single "propose plan"
  node whose one `interrupt()` call presents the entire plan object for one approval, with
  downstream nodes only reachable via the edge that fires after `Command(resume=...)` — this is
  effectively what the official
  [Plan-and-Execute tutorial](https://langchain-ai.github.io/langgraphjs/tutorials/plan-and-execute/plan-and-execute/)
  pattern already separates into a planner step vs. executor steps, just without a human gate
  between them by default (adding the gate is the natural extension, not a fight against the
  framework).
- **Local/offline**: `ChatOpenAI(base_url="http://localhost:<port>/v1", ...)` from `langchain-openai`
  talks to any OpenAI-compatible endpoint, including `llama-server`; no cloud SDK or vendor auth is
  structurally required — you can pass a dummy API key.
  [ChatOpenAI reference](https://reference.langchain.com/python/langchain-openai/chat_models/base/ChatOpenAI).
- **Constrained decoding**: `extra_body` is LangChain's documented, explicit mechanism for passing
  arbitrary non-standard JSON fields through `ChatOpenAI` to a custom OpenAI-compatible server
  untouched — e.g. `ChatOpenAI(base_url=..., extra_body={"grammar": "..."})` or a `json_schema`
  key, reaching `llama-server`'s native fields directly.
  [`extra_body` reference](https://reference.langchain.com/python/langchain-openai/chat_models/base/BaseChatOpenAI/extra_body).
  Separately, `with_structured_output(SomeModel, method="json_schema")` uses the *standard* OpenAI
  `response_format` structured-output convention, which `llama-server` also implements natively (see
  §0) — so there are **two independent paths to the hard guarantee**, one generic (`extra_body`)
  and one that happens to line up with a standard field llama-server already honors. Schemas can be
  built dynamically per call via `pydantic.create_model(...)` and passed as `args_schema`/output
  type at call time — confirmed as a standard, documented pattern, not a workaround.
- **Dynamic/runtime tool registration**: `StructuredTool.from_function(func, args_schema=<dynamic
  pydantic model>, ...)` is the documented, first-class way to build a tool at runtime from a
  freshly constructed schema — no decorator or import-time binding required; the `@tool` decorator
  is a convenience on top, not the only path.
  [StructuredTool reference](https://reference.langchain.com/python/langchain-core/tools/structured/StructuredTool).
- **Dependency weight / PyInstaller — the roughest edge found in this whole survey**: LangChain has
  multiple **open, unresolved GitHub issues specifically about PyInstaller freezing failures**:
  [langchain-ai/langchain#15386](https://github.com/langchain-ai/langchain/issues/15386) ("not
  `pyinstaller` friendly due to dependency on external files"),
  [langchain-ai/langchain#9264](https://github.com/langchain-ai/langchain/issues/9264) (`ImportError`
  for `lark` when frozen), plus a [pyinstaller org discussion](https://github.com/orgs/pyinstaller/discussions/8055)
  titled "Generating exe with langchain-module not possible?" These stem from LangChain's
  dynamic-import-heavy design (entry-point discovery, `importlib`, optional-integration probing) —
  exactly the pattern this repo's own CLAUDE.md already warns is fragile under PyInstaller (the
  `packaging/` shadow-directory gotcha is a different but same-genus problem: things that resolve
  fine in a normal venv silently break once frozen). Base `langgraph` + `langchain-core` +
  `langchain-openai` is a non-trivial transitive tree (pydantic, `langsmith` client, `tenacity`,
  `jsonpatch`, `httpx`, `PyYAML`, `typing-extensions`, and more) even before any other model-provider
  integration is added — heavier than the hand-rolled or Strands-minus-boto3 baselines.
- **Planning**: yes, an **official, maintained Plan-and-Execute tutorial/pattern** exists (planner
  node produces a plan, executor node(s) walk it) — the closest thing to an out-of-the-box
  plan-then-execute template found in this whole survey, though it does not ship a human-approval
  gate between planning and execution by default (you add the `interrupt()` yourself, which is
  straightforward given the pattern above).
- **Verdict: Good fit on capability, real cost on packaging risk.** LangGraph is the framework in
  this survey whose primitives most directly match "propose a plan as one interrupt-gated node,
  execute the rest deterministically," and its `extra_body`/`with_structured_output` paths both
  reach llama-server's hard constraint cleanly. The **documented, unresolved PyInstaller freezing
  issues** are a real, citable risk for a project whose CLAUDE.md already flags packaging/freezing
  as a known soft spot — this would need a dedicated freeze spike (and likely custom PyInstaller
  hooks) before committing, not just a "should be fine, it's pure Python" assumption.

## 6. Pydantic-AI

- **HITL**: **Deferred Tool Calls** — mark a tool `requires_approval=True`; when the model calls it,
  the agent run ends and returns a `DeferredToolRequests` object (tool name, validated args, unique
  call ID) instead of executing
  ([Deferred Tools docs](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/)). This is
  **structurally enforced per individual tool call** — the tool body itself is never invoked without
  a resolution step — but, like every other framework surveyed except LangGraph's native idiom, the
  primitive is per-tool-call, not "review the whole plan as one unit"; you'd get the whole-plan
  behavior the same way as elsewhere: make "submit the plan" the one `requires_approval` tool.
  **Resumption is documented as in-process/conversation-history-based** (pass `message_history` /
  `conversation_id` back in) — no durable, cross-process-restart session store was found in the
  docs (contrast with Strands' `FileSessionManager` and LangGraph's `SqliteSaver`/`PostgresSaver`);
  **flagging this as not fully verified either way** — Pydantic-AI shipped five releases in the two
  weeks before 2026-04-24 specifically adding "inline human-in-the-loop pauses," so a durable-session
  mechanism may exist that wasn't surfaced by the docs pages fetched; worth a direct check before
  ruling it out.
- **Local/offline**: `OpenAIChatModel` + `OpenAIProvider(base_url=...)` is the documented pattern
  for any OpenAI-compatible local server (shown against Ollama's `/v1` in the official docs); the
  same construction points at `llama-server`. No cloud SDK is structurally required for this path.
  [Ollama docs](https://pydantic.dev/docs/ai/models/ollama/).
- **Constrained decoding**: `NativeOutput` — "uses a model's native Structured Outputs feature (aka
  JSON Schema response format)" — maps to the OpenAI-standard `response_format` field, which
  `llama-server` implements natively (§0), so this should reach the hard grammar guarantee for any
  OpenAI-compatible `base_url`, not just recognized named providers — **this exact universality
  wasn't spelled out in the docs pages fetched, so treat as highly likely rather than fully
  confirmed**. Separately, a **real, verified gap**: [pydantic/pydantic-ai#1326](https://github.com/pydantic/pydantic-ai/issues/1326)
  documents that `model_settings` does not currently forward arbitrary non-standard fields (e.g.
  vLLM's `guided_json` convention) the way LangChain's `extra_body` does — so if you ever need a
  *non-standard* llama-server field, Pydantic-AI has no equivalent escape hatch today, only the
  standard `response_format` path. Dynamic schema per call is **confirmed via the API reference**
  (not just prose docs, which under-described this): `Agent.run(..., output_type=<dynamic type>)`
  is an explicit, documented override parameter — "Custom output type to use for this run" — so a
  freshly built `pydantic.create_model(...)` with computed enums can be passed per call.
  [Agent API reference](https://pydantic.dev/docs/ai/api/pydantic-ai/agent/).
- **Dynamic/runtime tool registration**: `FunctionToolset` instances can be constructed and passed
  at `agent.run()` call time (not just at `Agent()` construction), and `Agent(toolsets=...)` accepts
  functions that build toolsets dynamically from `RunContext` — plus `ToolPrepareFunc` for
  adding/removing/modifying tools between steps. Genuinely runtime-capable, comparable to Strands.
  [Toolsets docs](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/).
- **Dependency weight — a real surprise**: the top-level `pydantic-ai` PyPI package (as opposed to
  `pydantic-ai-slim`) is a meta-package whose `install_requires` is literally
  `pydantic-ai-slim[anthropic,cli,evals,google,logfire,mcp,openai,retries,web]` (verified directly
  from PyPI JSON metadata, version 2.21.0) — i.e. **installing "pydantic-ai" pulls in the Anthropic
  and Google Gemini client SDKs, an MCP client, a CLI, an evals harness, and Pydantic Logfire
  (a hosted observability product) by default**, none of which this fully-offline, single-local-model
  project needs. This directly contradicts the framework's "thin, no lock-in" reputation unless you
  know to depend on `pydantic-ai-slim[openai]` directly instead of the meta-package — an easy trap
  for a first-time integrator, and worth calling out explicitly since the reputation is what usually
  gets it on a shortlist in the first place.
- **Planning**: no built-in single-agent plan-then-execute template found; the companion
  **`pydantic-graph`** library offers a typed node/edge graph model (similar in spirit to
  LangGraph) for multi-step/multi-agent workflows, and a "Deep Agents" pattern in the docs
  explicitly discusses planning/progress-tracking as an architecture to assemble — but, same as
  LangGraph and Strands, the single-approval-on-one-plan-artifact behavior is application code you
  write, not a shipped primitive.
- **Verdict: Good fit, with one real dependency trap.** Once you deliberately install
  `pydantic-ai-slim[openai]` (not the `pydantic-ai` meta-package), the local-model story, the
  per-call dynamic schema story, and the runtime-toolset story are all solid and on par with
  LangGraph/Strands. The two open questions worth resolving with a spike before committing: whether
  deferred-tool state can be made durable across an app restart (needed for our "close the wallet
  mid-approval" case), and whether `NativeOutput` really forwards `response_format` untouched to an
  arbitrary `base_url` (very likely, given the OpenAI-compatible request format, but not found
  explicitly confirmed in the docs).

## 7. smolagents (Hugging Face)

- **Architecture mismatch worth flagging first**: smolagents' signature idea is the **`CodeAgent`**
  — the model writes and executes a block of **Python code** to call tools (with loops,
  conditionals, intermediate variables) rather than emitting one JSON tool call per turn. That is
  fundamentally incompatible with "constrain the single call to a JSON-Schema with `oneOf`+`const`+
  dynamic `enum`, hard": you cannot GBNF-constrain "arbitrary valid Python that happens to only call
  allowed functions with allowed arguments" the way you can constrain a single JSON object. smolagents
  does also ship a `ToolCallingAgent` variant that emits conventional JSON tool calls turn-by-turn —
  that variant is the one that could in principle be constrained, but then you're not using the
  library's differentiating feature.
- **HITL**: no first-class interrupt/approval primitive; the documented pattern is overriding
  `step()` or using `step_callbacks`/an `on_step` hook to inspect the pending action and raise
  `InterruptedError` to block it. This is a **callback convention**, not a structurally-enforced gate
  like LangGraph's `interrupt()`/Strands' `BeforeToolCallEvent` — a step callback that forgets to
  check would simply not stop anything.
- **Local/offline**: `OpenAIServerModel(api_base="http://localhost:8080/v1", ...)` connects to any
  OpenAI-compatible endpoint including `llama-server`; no cloud SDK required for that path.
- **Constrained decoding**: no evidence found of raw grammar/JSON-Schema pass-through to a custom
  backend; structured output support found in the docs is about typed output schemas for **MCP tool
  outputs**, not about constraining the model's own generation.
- **Dynamic/runtime tool registration**: tools are typically `Tool` subclasses/instances; can be
  constructed programmatically, but this wasn't confirmed to the same "build the whole manifest from
  a data-driven loop of JSON templates at runtime, no author-time coupling at all" degree as
  Strands/Pydantic-AI/LangChain's `StructuredTool.from_function`.
- **Dependency weight**: deliberately minimal core ("smol"), by reputation — not independently
  verified with a dependency count in this pass.
- **Planning**: `planning_interval` — the agent **re-plans every N steps** during execution, which
  is a "periodically reconsider strategy" loop, not a single upfront plan reviewed once before any
  execution — a different shape than what's needed here.
- **Verdict: Poor fit.** The code-agent paradigm that's smolagents' whole reason for existing is at
  odds with hard grammar-constrained single-call decoding; the `ToolCallingAgent` fallback loses that
  differentiation and still leaves HITL as a callback convention rather than a structural gate.

## 8. Microsoft Semantic Kernel (Python)

- **Planning — a real historical dead end, not a live option**: SK's dedicated planner
  abstractions (Stepwise, Handlebars, Action, Basic planners) have been **deprecated and removed**
  across Python/.NET/Java
  ([devblogs.microsoft.com/semantic-kernel — "The future of Planners"](https://devblogs.microsoft.com/semantic-kernel/the-future-of-planners-in-semantic-kernel/),
  [microsoft/semantic-kernel#12400, "Python: Remove SK planners"](https://github.com/microsoft/semantic-kernel/issues/12400)).
  The framework's own stated reasoning: once OpenAI-style native function calling became standard
  across providers, a separate "planner" abstraction stopped pulling its weight, and SK moved
  planning into plain function-calling loops. **There is no first-class plan-then-execute
  primitive left to borrow** — you'd build one on function-calling the same as everywhere else,
  except SK doesn't even offer the graph/DAG scaffolding LangGraph or `pydantic-graph` do.
- **HITL**: the documented pattern is "manual function calling" — you inspect which function(s) the
  model wants to call and decide yourself whether to invoke them — a **convention entirely in
  application code**, with no SDK-level structural gate found.
- **Local/offline**: SK lists an `ollama` extra and general OpenAI-connector support; an
  OpenAI-compatible custom endpoint should work through the same connector family, though a
  dedicated example pointed at `llama-server` specifically was not found and should be verified
  directly if pursued further.
- **Constrained decoding**: no evidence found of raw grammar/GBNF pass-through; SK's structured
  output story rides on the same provider-native `response_format`-style mechanisms as everyone
  else, layered with Pydantic-based settings validation.
- **Dynamic/runtime tool registration**: SK "plugins"/"functions" are typically decorated
  (`@kernel_function`) at import/class-definition time; dynamic registration from data was not
  confirmed.
- **Dependency weight**: the PyPI source distribution itself is small (~612 KB tarball for v1.41.3),
  but that measures SK's *own* code, not its transitive tree — base install pulls the OpenAI SDK by
  default, and the extras list is long (`aws`, `azure`, `chroma`, `faiss`, `google`, `mongo`,
  `pinecone`, `postgres`, `qdrant`, `redis`, `weaviate`, and more), signaling an enterprise
  multi-backend "big tent" design posture even though most extras are opt-in. **Total installed
  weight for just the local-model path was not independently measured** — flag as not fully
  verified.
- **Verdict: Poor fit.** The one thing that might have justified reaching for SK — a planner — was
  deliberately removed by its own maintainers in favor of exactly the "just do function-calling
  yourself" approach this project would do anyway; there's no compensating strength elsewhere
  (HITL is a manual convention, constrained decoding is unconfirmed, tool registration is
  decorator-bound) to justify the dependency.

## 9. AutoGen / AG2 (Microsoft-originated, community-forked)

- **Governance note worth flagging first**: AutoGen forked in 2024 into Microsoft's continuing
  `microsoft/autogen` (rewritten as an async, event-driven `autogen-core`/`autogen-agentchat` stack)
  and the community-led **AG2** (`ag2ai/ag2`, "the Open-Source AgentOS," formerly AutoGen) — two
  actively-developed lineages under similar names. Picking the wrong one, or assuming docs for one
  apply to the other, is a real integration risk; this section covers what's common to both.
- **Architecture mismatch**: both are fundamentally **multi-agent-conversation** frameworks —
  the core primitive is two or more agents (`AssistantAgent`, `UserProxyAgent`) exchanging
  messages. A single embedded assistant with one human and one model doesn't naturally need a
  conversation *between agents*; you'd be modeling "the human" as a `UserProxyAgent` purely to get
  at the `human_input_mode` knob, which is a shoehorn, not a natural fit.
  [AG2 human-in-the-loop guide](https://docs.together.ai/docs/autogen).
- **HITL**: `UserProxyAgent`'s `human_input_mode` (`ALWAYS`/`NEVER`/`TERMINATE`) is the primitive —
  a simple "ask before responding" gate, not a plan-hash-bindable checkpoint, and it's a
  conversation-turn convention rather than a structurally-enforced interrupt/resume mechanism with
  persisted state.
- **Local/offline**: extras like `ag2[ollama]` and general OpenAI-compatible client config support
  local/offline model backends; no hard cloud-SDK requirement for that path.
- **Constrained decoding**: AG2 docs confirm `response_format` (JSON Outputs) and `strict: true`
  tool-argument schemas are supported and described as preventing invalid responses "so there's no
  need for retries" — i.e., a hard-constraint claim, riding on the same standard OpenAI-compatible
  `response_format` field llama-server implements natively — this should reach the real guarantee
  for a llama-server backend, though not confirmed against llama-server specifically (docs examples
  shown were Anthropic/Bedrock-oriented).
- **Dynamic/runtime tool registration**: not independently confirmed to the same runtime-data-driven
  degree as Strands/Pydantic-AI/LangChain in this pass.
- **Planning**: no dedicated plan-then-execute primitive found beyond the general multi-agent
  conversation pattern (e.g., a "planner" agent conversing with an "executor" agent) — buildable,
  not shipped.
- **Verdict: Poor fit.** The conversational multi-agent core is solving a different problem than
  "one assistant, one local model, one human, one plan" — every capability that *is* there
  (HITL, structured output) is available more directly in frameworks built around a single-agent
  loop, without first modeling the human as a peer "agent" in a conversation.

## 10. Atomic Agents (BrainBlend-AI)

- **Core mechanism — the disqualifying finding**: Atomic Agents is explicitly "Built on Instructor
  and Pydantic." **Instructor is a retry-on-validation-failure library**: it sends a normal
  (unconstrained) request, validates the response against a Pydantic model, and re-prompts the model
  with the validation error if it fails — this is precisely the **soft** validate-and-retry
  mechanism the spec explicitly wants to avoid, not a hard sampler-level guarantee. No mention found
  of grammar/GBNF pass-through to any backend.
- **HITL**: no approval/interrupt primitives found; the framework has a general hooks system for
  "monitoring, error handling, and performance metrics," not human-approval gating.
- **Local/offline**: does support pointing at "any OpenAI-compatible API," which would extend to
  `llama-server`, though not demonstrated directly in the README.
  Instructor's own core dependency chain, however, doesn't buy you anything extra for the local
  path since the validation happens client-side regardless of backend.
- **Dynamic/runtime tool registration**: schemas in all examples found are static Pydantic classes
  defined at author time; no runtime/data-driven tool-manifest construction was found.
- **Dependency weight**: core is `Instructor` + `Pydantic`; provider SDKs (`instructor[groq]`,
  `instructor[anthropic]`, `instructor[google-genai]`) are extras, OpenAI included by default —
  reasonably light if you stick to the OpenAI-compatible extra only.
- **Maintenance**: actively developed — recent 2026 commits including a "V2.0" push and
  deriving `__version__` from package metadata — not a stale/abandoned project, unlike the
  concern raised for llama-cpp-agent.
- **Planning**: no plan-then-execute pattern found.
- **Verdict: Poor fit — specifically because of the soft-validation core.** This is close to a
  direct violation of constraint #5 (the spec explicitly rules out "validate-and-retry" as the
  mechanism): Atomic Agents' entire structured-output story *is* validate-and-retry by design, with
  no path found to the hard grammar guarantee. Everything else about it (light weight, active
  maintenance, OpenAI-compatible local support) is beside the point if the central mechanism is the
  one thing ruled out.

## 11. Comparison table

| Framework | HITL primitive | Local llama-server (HTTP) | Constrained decoding | Dynamic tool registration | Dependency weight | Planning | Verdict |
|---|---|---|---|---|---|---|---|
| **Hand-rolled loop** | build it — trivial, exact-fit | native, direct | native, direct — full raw pass-through | native, direct | `httpx`+`pydantic`(+`jsonschema`) only | build it | **Good fit** |
| **Strands Agents** (AWS) | structural (`interrupt`, `BeforeToolCallEvent`), durable (`FileSessionManager`); per-tool-call, not plan-level out of the box | dedicated `LlamaCppModel` HTTP provider, raw `grammar`/`json_schema` pass-through | hard, raw pass-through | yes — `TOOL_SPEC` dict + `ToolRegistry.register_tool()` | core forces `boto3`/`botocore`/`opentelemetry-*`/`mcp` unconditionally | `Graph`/`Workflow` DAG patterns, no single-plan-approval primitive | **Good, best-of-breed borrow candidate; weight is the cost** |
| **LangGraph** | structural (`interrupt`/`Command(resume=...)`), durable via `SqliteSaver`/`PostgresSaver`; graph shape makes single-plan-approval the natural idiom | `ChatOpenAI(base_url=...)`, generic OpenAI-compatible | hard via `extra_body` (raw) or `with_structured_output(method="json_schema")` (standard); dynamic via `pydantic.create_model` | yes — `StructuredTool.from_function(args_schema=<dynamic model>)` | heavy; **documented open PyInstaller-freeze GitHub issues** | official Plan-and-Execute tutorial (no human gate by default) | **Good fit on capability, real packaging risk** |
| **Pydantic-AI** | structural per-tool-call (`DeferredToolRequests`); durable cross-restart resumption **not confirmed** | `OpenAIProvider(base_url=...)` | hard via `NativeOutput`→standard `response_format` (likely, not 100% confirmed for arbitrary base_urls); non-standard `extra_body`-style passthrough is a confirmed gap (#1326); dynamic per-call `output_type` confirmed via API reference | yes — runtime `FunctionToolset`, `ToolPrepareFunc` | **meta-package `pydantic-ai` pulls in Anthropic+Google+MCP+Logfire by default** — use `pydantic-ai-slim[openai]` instead | no built-in single-agent plan template; `pydantic-graph`/"Deep Agents" pattern exists | **Good fit, mind the meta-package trap** |
| **smolagents** | callback convention (`step_callbacks`/`InterruptedError`), not structural | `OpenAIServerModel(api_base=...)` | none found; `CodeAgent`'s free-Python-code output is structurally incompatible with hard single-call grammar constraint | partial; not confirmed as fully data-driven | minimal by reputation (not independently measured) | `planning_interval` = periodic re-plan, not upfront single-plan approval | **Poor fit** — code-agent paradigm fights the hard-constraint requirement |
| **Semantic Kernel** | manual convention only | plausible via `ollama`/OpenAI connectors (not confirmed against llama-server specifically) | none found | decorator-bound (`@kernel_function`) | own code is small; transitive tree for local-only path not measured; many enterprise extras | **planners removed/deprecated** — no plan primitive left | **Poor fit** — planner deprecated, no compensating strength |
| **AutoGen / AG2** | `UserProxyAgent.human_input_mode` — conversational convention, not a checkpoint primitive | supported via extras/config | `response_format`+`strict` claimed hard (per AG2 docs), not confirmed vs. llama-server | not confirmed data-driven | moderate; governance split (Microsoft vs AG2 fork) adds selection risk | none dedicated; buildable via planner/executor agent conversation | **Poor fit** — multi-agent-conversation core is the wrong shape |
| **Atomic Agents** | none found | plausible via OpenAI-compatible extra | **Instructor = validate-and-retry (soft)** — the mechanism the spec rules out | static, author-time Pydantic classes | light (`Instructor`+`Pydantic` core) | none | **Poor fit** — central mechanism is exactly the soft path being avoided |
| **llama-cpp-agent** | none found | in-process bindings (`llama-cpp-python`-style), not confirmed HTTP-sidecar capable | native grammar/structured-output support (its whole purpose) | not confirmed data-driven | small, single-purpose | none | **Poor fit** — stale release cadence (PyPI tag 2+ yrs behind `master`, 25 open issues) plus unconfirmed HTTP-sidecar mode, too thin/risky for a shipped product |
| **Outlines** | N/A (decoding layer) | **in-process only** for llama.cpp (`llama-cpp-python`); remote-server support explicitly requested and unimplemented ([#513](https://github.com/outlines-dev/outlines/issues/513)) | would be hard if reachable, but isn't reachable here | N/A | N/A | N/A | **Not applicable / disqualified** — wrong architecture for a subprocess sidecar |
| **XGrammar** | N/A | No evidence of llama.cpp integration found; it's an in-process compiler for other engines (vLLM/SGLang/MLC) | N/A here | N/A | N/A | N/A | **Not applicable** — solves a problem this architecture doesn't have |

## Bottom line

**This project's constraints are narrow and unusual enough (single always-local provider, hard
grammar constraint as the primary correctness mechanism rather than a nicety, a bespoke
sign-the-plan-hash checkpoint, runtime-templated tools) that no framework earns its dependency
weight over a hand-rolled loop, but one framework — Strands Agents — is worth a real evaluation
spike as an alternative if the team would rather not own the loop.**

- **Hand-rolled loop over `httpx` → `llama-server`, using `/completion`'s native `grammar`/
  `json_schema` fields (or `/v1/chat/completions` `response_format` after confirming it behaves on
  your pinned build) is the recommended default.** Every "good fit" box — HITL exactly shaped to a
  plan-hash-bound crypto checkpoint, full raw grammar pass-through, genuinely runtime tool
  templates, minimal dependency footprint — is reached directly, with no framework's opinions about
  sessions/graphs/resume semantics to work around for the one gate that has to be
  unbypassable-for-real, not unbypassable-modulo-a-checkpointer.
- **Strands Agents (AWS)** is the strongest *borrow* candidate found — the only framework surveyed
  that combines a dedicated HTTP (not in-process) llama.cpp provider with raw grammar pass-through,
  a structurally-enforced interrupt with durable session persistence, and genuinely data-driven
  runtime tool registration (`TOOL_SPEC` dicts, no decorators required). Its cost is real: the base
  package unconditionally pulls in `boto3`/`botocore`/`opentelemetry-*`/`mcp` for a fully offline
  app that will never touch AWS — worth a PyInstaller freeze spike to see whether that weight is
  tolerable before ruling it in or out.
- **LangGraph** is the runner-up on capability — its graph model is arguably the most *natural* fit
  for "one interrupt-gated plan node, then deterministic executor nodes" of anything surveyed, and
  both `extra_body` and `with_structured_output` reach llama-server's hard constraint. It's held
  back by **citable, currently-open PyInstaller freezing issues** specific to LangChain's
  dynamic-import patterns — a real, documented risk for a project whose own CLAUDE.md already
  flags packaging fragility as a recurring pain point.
- **Everything else surveyed is a poor fit for a specific, named reason**: smolagents' `CodeAgent`
  paradigm structurally conflicts with hard single-call grammar constraint; Semantic Kernel removed
  the one thing (planners) that might have justified it; AutoGen/AG2's core abstraction is
  multi-agent conversation, the wrong shape for one assistant/one human; Atomic Agents' entire
  structured-output mechanism is Instructor's validate-and-retry — the specific soft mechanism
  constraint #5 rules out; Outlines/XGrammar solve a problem (getting hard constraint out of an
  engine that doesn't have it) that this architecture doesn't have, because llama-server already
  constrains natively; llama-cpp-agent is conceptually the closest fit but too thin and stale
  (2+-year-old PyPI release vs. `master`) to bet a shipped product on.
- **Honest hybrid, if "none fit cleanly" needs a sharper answer**: hand-roll the loop and the
  checkpoint (because nothing ships the plan-hash-bound signing ceremony, ever, by construction —
  that's this project's KERI-native design decision to own, not a framework's), but freely borrow
  ideas rather than code from LangGraph's plan-and-execute node shape and from Strands' `TOOL_SPEC`
  convention for how to shape the runtime tool manifest. That gets the benefit of frameworks that
  have already thought hard about these exact problems without inheriting their dependency trees.
- **Independent of framework choice — two findings likely to matter more than the framework
  decision itself**: (1) the **"constraint tax" / Tool Suppression** finding (§0) — a single
  decoding pass that's asked to both decide *whether/which* tool to call and produce
  perfectly-shaped arguments can suppress tool-calling entirely under hard grammar constraint;
  structure turns as a decide-pass then a constrained-fill-pass. (2) **large dynamic enums are a
  documented performance risk** in llama.cpp's native grammar engine — budget time to evaluate the
  opt-in LLGuidance backend (`-DLLAMA_LLGUIDANCE=ON`, requires adding Rust/cargo to the build) if
  the session-valid identifier/schema-hash enums grow large.

### What could not be verified (flagged honestly, not guessed)

- Whether Pydantic-AI's deferred-tool-call state can be made durable across an app/process restart
  (docs describe in-process/conversation-history resumption; a durable session store may exist but
  wasn't found in the pages checked).
- Whether Pydantic-AI's `NativeOutput` forwards the standard `response_format` field untouched to
  an arbitrary OpenAI-compatible `base_url` (very likely given the wire-format, not explicitly
  confirmed in docs).
- Whether Strands Agents or LangGraph/LangChain have specific, working PyInstaller hooks (none
  found for Strands, either positive or negative; LangChain has multiple **open, unresolved**
  freezing issues, so "there's a known problem" is confirmed even though "here's the exact current
  fix" is not).
- Semantic Kernel's and AutoGen/AG2's constrained-decoding behavior specifically against a
  `llama-server` backend (both claim standard `response_format`/`strict` support in general, neither
  was confirmed against llama-server in particular).
- Whether `/v1/chat/completions`'s `response_format` + `--jinja` (needed for tool-calling chat
  templates) is fully clean on current llama.cpp — historically buggy (fixed Feb 2025 per
  [#11847](https://github.com/ggml-org/llama.cpp/issues/11847)), but a same-week follow-up comment
  reported a related formatting glitch right after the fix landed; recommend smoke-testing this
  exact combination on your pinned commit rather than assuming it's clean.
- Precise transitive dependency *counts/sizes* (as opposed to named packages) for LangGraph,
  Pydantic-AI-slim, Semantic Kernel, and AutoGen/AG2 — named the heavy/notable packages found via
  PyPI metadata where checked (Strands, Pydantic-AI meta-package) but did not do a full `pip install
  --dry-run` size audit for every framework; recommend that as a concrete next step before a final
  decision, especially for whichever of LangGraph/Strands survives to a spike.
