# plan/

## Purpose
Short-lived plans for work that is about to start, possibly on another branch or by another agent.
Plans are tracked so every branch, worktree, and agent sees the same ones.

## Usage
- One file per piece of work. Self-contained: a fresh agent should be able to start from the file alone.
- **Short-lived.** Delete the file in the same PR that ships the work (or in the PR that abandons it).
  The record then lives in the commit messages and the docs. A plan that outlives its work is stale
  by definition; do not leave one behind to be trusted by the next reader.
- Durable decisions do not belong here. Put them in an ADR (`docs/adr/`) or a reference doc.
- Mark anything unverified as unverified. A plan that states a guess as fact sends the next agent the
  wrong way.
- Plans hold no secrets, account numbers, or private strategy parameters. Anything tracked here is
  public; private notes belong under `local/` (see `AGENTS.md`).
- Keep the Status line current: drafted, in progress (branch name), or blocked (on what).

## Index
| Plan | Status | Depends on |
|---|---|---|
| [more-trading-evidence.md](more-trading-evidence.md) | Drafted 2026-10-09; design B (a periodic intraday job, built as a scheduler repeat interval) chosen 2026-10-19. Nothing run on the host. | none (contract-trading-rules.md is related) |
| [distinct-books.md](distinct-books.md) | Items 1-4 merged (#332-#335); item 5 (broker cash check) built on feature/broker-cash-check, not yet run on the host. See its "Left to do". | none (more-trading-evidence.md is related) |
| [ib-gateway-socket-switch.md](ib-gateway-socket-switch.md) | In progress on `feature/ib-gateway-socket-switch`; host trial partly run 2026-11-11. | none (the socket adapter is merged) |
| [legibility-shared-types.md](legibility-shared-types.md) | Drafted 2026-11-11. Item 1 built on `feature/side-and-gate-action-vocabulary`, not committed; items 2-5 not started; no owner question open. | none |
| [contract-trading-rules.md](contract-trading-rules.md) | Drafted 2026-10-09. IBKR rules endpoint not yet checked on the host. | PR #294 (reconcile lookup) merged; PR #293 is merged |
