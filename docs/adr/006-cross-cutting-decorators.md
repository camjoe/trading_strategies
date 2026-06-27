# ADR: Sanction Decorators and Context Managers for Cross-Cutting Concerns

Type: adr
Status: Accepted
Created: 2026-06-27
Last Reviewed: 2026-06-27
Purpose: Establish a sanctioned, bounded pattern for extracting repeated cross-cutting boilerplate (setup/teardown, skip-guards, error→exit-code mapping) using decorators and context managers, starting with the runtime governance jobs.
Related: [Architecture Conventions](../architecture/architecture-conventions.md), [General Style](../conventions/general-style.md), [Trading Package Map](../maps/trading-package-map.md)

## Context

The codebase currently has **no custom decorators** — only stdlib `@lru_cache`
and `@runtime_checkable`. This has been deliberate: our conventions prize
explicit control flow over magic, and for most of the project's life the
duplication did not justify a new abstraction.

The project has now grown to where that trade-off is shifting. The clearest
instance is the runtime job layer. Six governance jobs
(`governance/weekly/w1`–`w3`, `governance/monthly/m1`–`m3`) share a
near-identical `main()` skeleton — roughly 40 lines each of the same scaffolding:

1. parse the same `--accounts` / `--force-run` / `--repo-root` flags
2. resolve `repo_root`, build + `mkdir` the logs/artifacts dirs
3. compute the period tag, build `log_path` and `artifact_path`
4. write the `RUN META` log line
5. run the `skip_if_already_completed_for_period` guard (early `return 0`)
6. `try: <real work> → write_artifact → tee COMPLETE_SENTINEL` /
   `except Exception → tee ERROR, return 1` / `finally: conn.close()`

Only the body inside `try` differs per job. The helpers in
`interfaces/runtime/jobs/job_helpers.py` already exist; they are just wired in by
hand in every file. This is ~240 lines of mechanical repetition with a single
cleanly-isolated point of variation — the canonical case for extracting a
cross-cutting wrapper.

We expect this shape to recur beyond governance jobs (daily jobs share parts of
it; UI-backend routes repeat a domain-error→`HTTPException` mapping; feature
providers repeat a graceful-degradation `try/except`). Rather than solve the
governance case ad hoc, this ADR sets the **bounded pattern and placement rules**
so future extractions are consistent and do not erode the "explicit by default"
culture.

Alternatives considered:

- **Status quo (helper functions called inline).** Rejected: keeps the 40-line
  skeleton visible in every file; the duplication is now large enough that drift
  between jobs is a real maintenance risk.
- **Plain template/runner function** (`run_governance_job(spec, body_fn)`).
  Viable and the most conservative; functionally equal to a decorator without
  `ParamSpec` typing cost. Rejected as the *primary* recommendation only because
  the `@`-annotated call site reads more clearly and signals "this is a standard
  job" at a glance — but see Decision §5, it remains the sanctioned fallback when
  a decorator would obscure more than it clarifies.
- **Inheritance / a `Job` base class.** Rejected: heavier, couples jobs through a
  class hierarchy, and fights the functional style of the existing job modules.

## Decision

1. **Decorators and context managers are sanctioned for cross-cutting concerns
   only** — resource setup/teardown, timing/instrumentation, retry, skip-guards,
   error-to-result mapping, registration. They must **not** carry business or
   domain decision logic, and must **never** appear in `src/trading/domain/` or
   `src/trading/models/`, where explicit control flow is required.

2. **Split the concern by tool.** When a concern is *setup + guaranteed
   teardown* (open log, open DB connection, `finally: close`), use a
   `contextlib` **context manager** — not a hand-rolled `try/finally` inside a
   decorator. When a concern is *wrapping the call* (early-return guards,
   `except → return code`, success sentinel), use a **decorator**. The two
   compose: a decorator may drive a context manager internally.

3. **Placement follows the lowest-owning-layer rule.** A cross-cutting helper
   lives at the lowest layer that owns the concept:
   - Generic, domain-agnostic (timing, retry, simple caching) → `src/common/`
     (e.g. `src/common/decorators.py`).
   - Concern that knows about an interface concept (CLI exit codes, log paths,
     job sentinels, HTTP responses) → that interface area, **not** `common/`.
     The governance-job runner therefore lives in
     `src/trading/interfaces/runtime/jobs/` (e.g. `job_runner.py`), beside
     `job_helpers.py`.
   - The standard module name is `decorators.py` (or a runner/session module when
     it also exposes a context manager).

4. **Typing and hygiene are mandatory.** Every wrapper uses `functools.wraps` and
   preserves the wrapped signature with `typing.ParamSpec`/`TypeVar` so `mypy`
   (CI) sees no degradation. Parameterized decorators are written as decorator
   factories. No bare `Callable[..., Any]` passthroughs.

5. **Prefer the plainest tool that removes the duplication.** A decorator is not
   automatically correct. If a context manager alone, or a plain runner function,
   removes the duplication with clearer control flow, use that. Reserve
   decorators for cases where the `@`-annotation genuinely improves the call site.

6. **First application (this ADR's proof case):** introduce a
   `governance_job(*, job_name, sentinel, period)` decorator factory in
   `src/trading/interfaces/runtime/jobs/job_runner.py`, backed by a
   `contextlib` job-session context manager that owns the logs/artifacts/DB
   lifecycle and the skip-guard. Each governance job becomes a small body that
   receives a `JobContext` and returns a payload dict. Migrate one job (`m1`)
   first as a reviewed proof, then the remaining five. **Status: complete — all
   six governance jobs (`m1`–`m3`, `w1`–`w3`) are migrated, the 73 governance
   tests pass, and ruff/mypy/layer-check are clean. The runner grew two job
   hooks during migration: `add_arguments` (custom CLI flags) and `validate`
   (pre-run arg checks). See Findings below.**

## Consequences

Benefits:

- ~240 lines of duplicated job scaffolding collapse to one wrapper plus six small
  bodies; the variation per job is all that remains visible.
- A single, typed, tested place owns job lifecycle, skip semantics, and
  error→exit-code mapping — drift between jobs becomes impossible.
- A documented, bounded pattern exists for the next cross-cutting case
  (daily jobs, UI error mapping, provider degradation) instead of ad-hoc choices.

Trade-offs / constraints imposed:

- This is a deliberate departure from "zero custom decorators." The guardrails in
  Decision §1 and §5 exist to keep it from spreading into business logic.
- A wrapper adds one layer of indirection at the call site; stack traces pass
  through the wrapper. `functools.wraps` keeps names/docs intact, but reviewers
  must still look one level up to read the lifecycle.
- `ParamSpec`-typed wrappers are slightly more verbose to author correctly.

Findings from the `m1` proof (2026-06-27):

- **The real per-job cost is moving the test seam, not the code.** Our runtime-job
  tests monkeypatch dependencies as attributes *on the job module*
  (`module.ensure_db`, `module.resolve_accounts`,
  `module.load_runtime_eligible_account_names`). Once those calls move into the
  shared `job_runner`, every patch that targeted them must move to `job_runner`.
  For `m1` this meant: making the shared `stub_runtime_job_basics` helper patch
  `job_runner` too (additive + `hasattr`-guarded, so un-migrated jobs are
  untouched), and repointing three `m1` tests. The subtlest was the
  `run_module_as_main` entrypoint test, which had relied on `runpy` re-executing
  `m1`'s `from ... import` line to observe a patch on the *source* module; with
  the call now in already-imported `job_runner`, the patch had to target
  `job_runner`. Each remaining job will carry the same kind of test-seam edit —
  small and mechanical, but real, and the reason migration is one-job-at-a-time
  with the suite run after each.
- **Decision §4's `ParamSpec` rule applies to signature-*preserving* decorators,
  not this one.** `governance_job` deliberately *transforms* the signature
  (`(JobContext) -> dict` into `() -> int`), so `ParamSpec` does not apply; it is
  typed instead with explicit `Callable` aliases (`JobBody` and a
  `Callable[[JobBody], Callable[[], int]]` return), `mypy`-clean with zero `Any`.
  Read §4 as: preserving wrappers (retry/timing) use `ParamSpec`; transforming
  wrappers use explicit `Callable` types. Either way, no bare `Callable[..., Any]`.

Follow-ups:

- [x] Implement Decision §6 and migrate the six governance jobs.
- [x] Add a short "Cross-Cutting Patterns" subsection to
  `docs/architecture/architecture-conventions.md` capturing Decision §1–§5.
- [x] Note the new `job_runner.py` module in `docs/maps/trading-package-map.md`.
- [ ] Re-evaluate daily jobs, UI error mapping, and provider degradation against
  this pattern as separate, individually-scoped changes — do not batch them.
