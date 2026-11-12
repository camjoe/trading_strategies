# Plan: make the daily paper-trading run read as a list of steps

Status (2026-11-11): drafted. Nothing built. One owner decision is open (item 4).

Keep this file until the "Left to do" list is empty.

## Left to do
Check these off in the pull request that does each one; delete this file when none remain.
1. **Item 1, move the step bodies** out of `workflow.py` into `steps.py`.
2. **Item 2, move the run outcome** (artifact payload, alert message, exit code) into `outcome.py`.
3. **Item 3, flatten `run_workflow`** so each step is one call to a top-level function.
4. **Item 4, correct two step display names.** Needs the owner's yes first.

## Goal
Make the daily run quick to read. Opening `workflow.py` should show the eleven steps in order, one call each,
and each step's work should be a named top-level function a reader can jump to.

This is a readability refactor. **Items 1-3 change no behaviour**: the run artifact, the log lines, the
notification text and status, the exit code, the subprocess commands, and the step ids, order, statuses, and
details all stay the same. An item that cannot be done without changing one of those stops and asks. Item 4 is
the one place a written value changes, and it is held for a decision.

## What exists (verified in the code, 2026-11-11)
Names, not line numbers; lines move. All paths are under
`src/trading/interfaces/runtime/jobs/daily/paper_trading/`.

- **`workflow.py` is 785 lines and holds four different things**: subprocess step bodies, readers that pull
  facts back out of step results, the end-of-run artifact and alert, and the orchestration itself.
- **`run_workflow` is 233 lines.** It defines five closures (`_ingest_market_and_account`, `_pre_trade_step`,
  `_run_shadow_eval`, `_run_all_auto_trader_groups`, `_run_compare_strategies`). Two of them rebind
  `context` or `skipped_accounts` through `nonlocal`, and the function re-reads `accounts` and
  `account_trade_caps` from `context` after each rebind.
- **`_finish_run` is 126 lines.** It builds the artifact payload, builds the alert message in three branches
  (failed, completed with notes, clean), picks the alert status, writes the artifact, and sends the
  notification.
- **The step table already exists.** `DAILY_DAG_STEPS` in `dag.py` pairs each step id with a display name, and
  its comment says the ids are a persisted contract and no longer describe the work. `dag.py` also owns
  `DagStepResult`, `run_dag_step`, `skip_dag_step`, and `StepFailedError`.
- **Two display names are out of date.**
  - `00_ingest_market_and_account` is named "Resolve run context (accounts and trade caps)". The step calls
    `check_broker_sessions` and records which accounts were skipped; the run context is built earlier, in
    `main`.
  - `01_mark_book_nav` is named "Reconcile fills and snapshot equity (pre-trade)". It also reconciles pool
    mates outside the run and runs the broker cash check (`pre_trade_reconcile_and_cash_check`).
- **The display name is written to every run artifact** (`DagStepResult.name` through `as_dict`).
- **Step ids are read from artifacts** by `maintenance/burn_in_status.py` (`FIRST_ORDER_STEP_ID`, and a string
  comparison on `failed_step`), `maintenance/replay_daily_runs.py`, and
  `trading/services/autonomy_monitor/artifacts.py`. Seven docs under `docs/` name step ids.
- **Steps pass results between processes as stdout lines.** `_broker_anomaly_accounts` and `_unresolved_orders`
  parse lines that start with `BROKER_ANOMALY_LINE_PREFIX` / `UNRESOLVED_ORDERS_LINE_PREFIX`. This plan leaves
  that mechanism alone.
- **Tests reach into `workflow` by name.** Seven test modules under
  `tests/src/trading/interfaces/runtime/jobs/daily/` import it. They patch `run_command`, `stream_command`,
  `tee_line`, `check_broker_cash`, `check_broker_sessions`, `pool_mates_outside_run`, and `_unresolved_orders`
  on the module (some through `tests/.../jobs/loaders.py`'s `DAILY_PAPER_TRADING_WORKFLOW_MODULE` string), and
  call `snapshot_account_with_retry`, `kill_switch_accounts_from_dag`, `build_run_summary`,
  `run_auto_trader_group`, and `catch_up_command` directly.
- **A function-size check exists**: `scripts/checks/python/function_complexity_check.py`, with
  `MAX_FUNCTION_LINES = 100`. **Unverified:** whether it is advisory or enforced, and in which profile.

## Target layout
```
paper_trading/
  dag.py        step table, DagStepResult, run/skip helpers          (unchanged apart from item 4)
  steps.py      what each step does                                  (new, item 1)
  outcome.py    what the run leaves behind: artifact, alert, exit    (new, item 2)
  workflow.py   run_workflow only: the steps in order                (item 3)
```

## Work items
One pull request per item, in order. Each passes the gate on its own.

### 1. Move the step bodies into `steps.py`
A pure move. Function bodies are not edited.

- Move: `run_auto_trader_group`, `_broker_anomaly_accounts`, `snapshot_account_with_retry`, `reconcile_fills`,
  `reconcile_and_snapshot`, `_unresolved_orders`, `_unresolved_in`, `skip_accounts`,
  `pre_trade_reconcile_and_cash_check`, `BrokerAnomalyError`, `SNAPSHOT_MAX_ATTEMPTS`, and
  `SNAPSHOT_BACKOFF_SECONDS` (with their comments).
- Move `catch_up_command` and `_interpreter_for` to `run_context.py`, beside `exclude_accounts`, which already
  takes the command as an argument. `skip_accounts` and the outcome code both use it.
- No re-exports from `workflow.py` (architecture conventions, Import and Facade Rules). Update the tests to
  import and patch the new module: a patch has to target the module that looks the name up, so
  `check_broker_cash`, `check_broker_sessions`, `pool_mates_outside_run`, `run_command`, `stream_command`, and
  `tee_line` patches move with the functions that call them. Add a `steps` module constant to `loaders.py`
  beside the workflow one.
- `_unresolved_in` is used by both the step bodies and the outcome readers. It stays private to `steps.py` in
  this item; item 2 decides where the outcome side gets it from (see there).

### 2. Move the run outcome into `outcome.py`
- Move unchanged: `kill_switch_accounts_from_dag`, `broker_anomaly_accounts_from_dag`,
  `unresolved_orders_from_dag`, `_describe_unresolved`, `_int_field`, `_sum_account_field`, `build_run_summary`,
  and `COMPLETE_SENTINEL`.
- `_unresolved_in`: make it public in `steps.py` under a name that says what it reads, and import it here. Do
  not copy it.
- Split `_finish_run` into three functions, called in the same order it runs today:
  - one that builds the artifact payload (a `build_*` name),
  - one that builds the alert message and one that picks the alert status. Both take the same facts (failed,
    error, kill-switch accounts, skipped accounts, anomaly accounts, unresolved orders, step results) and have
    no side effects, so they can be tested without a log file or a notifier. Name the message one `render_*`;
    it is operator-facing display text.
  - `finish_run`, which calls those, writes the artifact, sends the notification, and returns the exit code.
- The message text is read by the operator and may be matched in tests. Move the string literals; do not
  reword them. A changed character in a message is a stop.
- Tests: before the split, add a test that pins the full message and status for each of the three branches
  (failed with an earlier anomaly, completed with every kind of note, clean). It must pass on the code as it is
  and again after the split with no edits. **Unverified:** how much of this the existing
  `test_daily_paper_trading_state.py` and `test_run_summary.py` already pin; read them first and extend rather
  than duplicate.

### 3. Flatten `run_workflow`
- Replace the five closures with top-level functions in `steps.py`, one per step that does work:
  check broker sessions (00), shadow evaluation (02), run the trading books (05), compare strategies (09).
  `pre_trade_reconcile_and_cash_check` (01) is already top-level.
- Replace the `nonlocal` rebinding with one small mutable state object passed to each step. It holds what the
  closures share today: the initial context, the current context, the step results, and the shadow-evaluation
  summary. Steps read `state.context.accounts` when they run, which removes the repeated
  `accounts = context.accounts` re-reads. Put it in `run_context.py` or `steps.py`, whichever avoids an import
  cycle.
- `run_workflow` then reads top to bottom as one `run_dag_step` or `skip_dag_step` call per step, with the
  shadow-evaluation branch as its only conditional, followed by the sentinel line and `finish_run`. Give it a
  docstring that says what it returns and that a failure in any step still reaches `finish_run`.
- Do **not** build a generic step runner that loops over `DAILY_DAG_STEPS`. Steps 02-04 are conditional and
  the explicit calls are what a reader wants to see.
- Keep exactly: the order of steps, which exceptions each step raises or wraps (`BrokerAnomalyError`,
  `StepFailedError`), when `context` is replaced (after step 00 and after step 01), and that step 05 trades
  with the post-skip accounts and caps.
- Done when no function in the package is over the limits in `function_complexity_check.py`. Report any that
  still is.
- Tests: the existing workflow, state, seam, and end-to-end daily tests pass with only import and patch-target
  edits. An expected artifact value or message that has to change is a stop.

### 4. Correct two step display names (held for the owner)
Change only the display names in `DAILY_DAG_STEPS`; the ids stay.

- `00_ingest_market_and_account`: say that it checks broker sessions and skips accounts that cannot connect.
- `01_mark_book_nav`: add the pool-mate reconcile and the broker cash check.
- Also correct the sentence in the `workflow.py` module docstring if item 3 left it describing the old shape.
- This changes the `name` field in run artifacts written after the change; old artifacts keep the old names.
  **Unverified:** whether anything compares `name` (the autonomy monitor panel in
  `apps/paper_trading_web/frontend/src/components/autonomy-monitor-panels.ts` shows step results; a search of
  the backend and the maintenance jobs found no reader of `name`). Search the frontend and its tests before
  editing, and list what reads it in the pull request.

## Constraints
- Read `docs/architecture/architecture-conventions.md` in full before editing `src/trading/`.
- A file move and a behaviour change are separate steps. Items 1 and 2 are moves; do not tidy a body while
  moving it.
- The trading step shells out to `run_auto_trades` and that path submits orders. Nothing here touches
  `run_auto_trades.py`, `reconcile_orders.py`, `broker_preflight.py`, or anything under `trading/services/`.
- No comments that narrate the change. Rationale goes in commit messages.
- Nothing here is strategy-specific; all of it is intentionally public.
- Docs that name the file: the `daily/paper_trading/workflow.py` row in `docs/maps/trading-package-map.md`
  (add rows for the new modules) and the pointer in `docs/reference/runtime-jobs.md`. Update them in the pull
  request that moves the code. `plan/ib-gateway-socket-switch.md` also mentions `workflow.py` and
  `stream_command`; fix that line if that plan still exists.
- Run `python -m scripts.fix_checks`, then `python -m scripts.run_checks pr --base origin/develop`.
- **Environment (seen 2026-11-11 on the dev PC):** the `.venv` editable install resolved to a different
  checkout, so `pytest` failed on import until `PYTHONPATH` pointed at this checkout's `src` and `apps`. If
  imports fail the same way, report it; do not reinstall the environment unasked.

## Decisions needed (owner)
- Item 4: whether to change the two display names, given that it changes the `name` field in new run artifacts.

## Out of scope
- Renaming or renumbering step ids. They are a persisted contract.
- Replacing the stdout-line hand-off between the workflow and its subprocesses with a structured result.
- Moving orchestration out of `interfaces/` into `trading/services/`. The steps shell out to other job modules,
  which is scheduler transport; a service-level daily run would be a design change, not a tidy-up.
- Typing `DagStepResult.details`. `plan/legibility-shared-types.md` records the owner's decision to keep it
  `dict[str, object]`.
- Splitting `job_helpers.py`.

## Developer verification (fill in when the work ships)
- Items 1-3: `python -m scripts.checks.run_suite src/trading/interfaces --no-cov` and the three
  `tests/e2e/test_daily_paper_trading_*` files pass; a dry daily run against a sandbox database writes an
  artifact whose keys and step ids match one written before the change.
- Item 4: to be filled in.
