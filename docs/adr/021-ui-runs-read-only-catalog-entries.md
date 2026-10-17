# ADR: The web UI runs read-only catalog entries

Type: adr
Status: Proposed
Created: 2026-10-03
Last Reviewed: 2026-10-03
Purpose: Records that the web UI may start a command from the generated catalog, which commands qualify, and the limits on how the backend starts one.
Related: [architecture-conventions.md](../architecture/architecture-conventions.md), [007-ui-error-mapping.md](007-ui-error-mapping.md)

## Context

The Catalog tab lists every CLI command, runtime job, script, and check, generated from the code into
`apps/paper_trading_web/frontend/src/assets/commands.json`. A Run button on each entry lets a person see
real output without a terminal.

The UI Backend Boundary Rule says `backend/services/` holds only request conversion, error handling,
and response shaping. Starting a process is none of these, so the runner needed an explicit decision.
The rule exists to keep domain logic out of the UI backend. The runner has none: it starts the project's
own entry points, which stay available in the CLI.

Options considered:

1. **Run commands in `backend/services/` and amend the rule.** One place for UI transport code; the rule
   and the code agree.
2. **Put the runner in a new package beside `services/`.** This avoids the rule by naming, not by
   substance, and hides the exception.
3. **No Run button.** The catalog shows commands only. Safe, but a visitor cannot see the system work.

## Decision

Option 1. `backend/services/catalog_runner.py` runs one catalog entry as a subprocess. The Boundary Rule
lists this as an allowed content type.

Which entries run is data, not code:

- An entry runs only if the registry marks it `runnable`. The registry builder refuses to mark an entry
  runnable unless its risk is `read-only`.
- Entries that write data, reach a broker, take minutes, install packages, or run the test suite are
  not listed in `RUNNABLE_TOOLS` or are named in `NOT_RUNNABLE_FROM_UI`. A new entry is not runnable
  until someone lists it.

How a command starts:

- The runner validates every value against the entry's own argument definition (type, choices, one line,
  no unknown names). It writes options as `--flag=value`, places global options before the subcommand,
  rejects positional values that start with `-`, and starts the process without a shell and with stdin
  closed.
- A run stops after 60 seconds. Output is cut at 200,000 characters. One run at a time is allowed.
- The route refuses a browser request whose `Origin` is not this machine, because the API allows every
  origin.
- The backend reads `commands.json` from the frontend assets folder. A missing file returns 503 with the
  command that rebuilds it.

## Consequences

- Risk labels now carry safety weight. A wrong `read-only` label on a command that writes would let the UI
  run it. Every runnable entry was run against the demo database and changed no data; a new entry needs
  the same check.
- The child process finds its database through `TRADING_DB_PATH`, as the launchers set it.
- Output is returned when the command ends, not streamed. This is enough while runnable commands finish
  in seconds.
- The backend depends on the frontend assets path. Moving the registry needs a change in
  `backend/config.py`.
- The concurrency lock is per process. A multi-worker deployment needs a shared lock. The UI is local-only
  today.
