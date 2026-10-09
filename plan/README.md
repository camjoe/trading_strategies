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
| [review-mindsets.md](review-mindsets.md) | Drafted 2026-10-09. Pilot not run. | none |
| [more-trading-evidence.md](more-trading-evidence.md) | Drafted 2026-10-09. Nothing run on the host. | none (contract-trading-rules.md is related) |
| [contract-trading-rules.md](contract-trading-rules.md) | Drafted 2026-10-09. IBKR rules endpoint not yet checked on the host. | PR #294 (reconcile lookup) merged; PR #293 is merged |
