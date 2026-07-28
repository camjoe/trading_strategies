# ADR: IBKR paper is its own broker type, not a live-guard exception

Type: adr
Status: Accepted
Created: 2026-07-27
Last Reviewed: 2026-07-27
Purpose: Record why IBKR paper connectivity gets its own `broker_type` with a positive paper-account assertion, instead of being reached by enabling the real-money `live_trading_enabled` guard.
Related: [Broker Integration](../reference/broker-integration.md), [IBKR Paper Execution Plan](../reference/ibkr-paper-execution-plan.md), [Architecture Conventions](../architecture/architecture-conventions.md)

## Context

`live_trading_enabled` was introduced to stop real money moving by accident. Its
documented rationale is explicit: "`live_trading_enabled = 1` causes real money to move
through a live broker."

In practice the flag guarded something broader than its rationale. Every IBKR path —
`interactive_brokers_web` and the socket-compatible `interactive_brokers` — required the
flag, whether the configured Client Portal account was a live account or a paper one.
IBKR paper accounts are real IBKR infrastructure (real order mechanics, real rejections,
real partial fills, real market data) with no capital at risk, but the factory had no way
to express that. There were two states: the internal simulator, or "real money allowed".

The consequences were concrete:

1. Every account in the system fell through to `PaperBrokerAdapter`, which accepts every
   order and fills it in full, instantly, at the requested price, with zero commission
   and no possibility of rejection or slippage.
2. Reaching IBKR at all — even a `DU` paper account — meant setting the real-money flag,
   which the Live Trading Safety Guard forbids automation from doing and which an
   operator should not do to run a test.
3. Nothing verified that a `live_trading_enabled = 1` account was pointed at a live or a
   paper Client Portal account. The flag authorized the *adapter*, never the *account*.
   An operator who enabled it for paper testing had no guardrail left if the configured
   `account_id` was later changed.

So the guard simultaneously blocked a safe activity and under-protected a dangerous one.

Alternatives considered:

- **Enable `live_trading_enabled` on a paper-configured account.** Rejected: conflates
  connectivity with capital risk, is forbidden for automated processes, and leaves the
  configured account identity unverified.
- **Add a separate `paper_broker_enabled` account column.** Rejected: requires a
  migration, and broker routing already belongs to `broker_type` — the factory is the
  sole location for `broker_type` routing logic.
- **Infer paper vs. live from the `account_id` prefix without a new broker type.**
  Rejected: makes the routing decision implicit, so a configuration typo would silently
  change the account's safety posture rather than failing loudly.

## Decision

Add `broker_type = 'interactive_brokers_paper'` as a first-class broker type.

It routes through the same `InteractiveBrokersWebAdapter` and Client Portal client as
`interactive_brokers_web`, and:

1. **Does not require `live_trading_enabled`.** That flag now guards only real-money
   paths, matching its stated rationale.
2. **Positively asserts the account is a paper account.** The resolved
   `account_id` must start with the IBKR paper-account prefix `DU`. If it does not, the
   factory raises `PaperBrokerAccountMismatchError` and refuses to connect.

The existing guard on `interactive_brokers_web` and `interactive_brokers` is unchanged:
both still raise `LiveTradingNotEnabledError` without `live_trading_enabled = 1`.

No migration is required — `accounts.broker_type` is `TEXT NOT NULL DEFAULT 'paper'`
with no CHECK constraint.

The resulting routing table:

| `broker_type` | Adapter | Requires `live_trading_enabled` | Account assertion |
|---|---|---|---|
| `paper` (default) | `PaperBrokerAdapter` (simulator) | no | none — never leaves the process |
| `interactive_brokers_paper` | IBKR Web API | **no** | **`account_id` must start with `DU`** |
| `interactive_brokers_web` | IBKR Web API | yes | none (operator-owned) |
| `interactive_brokers` | IBKR socket/TWS | yes | none (operator-owned) |

## Consequences

**This is a net increase in safety, not a relaxation.** Three things improve at once: the
paper path gains an account assertion it never had; the real-money flag regains the
narrow meaning its rationale always claimed; and the standing incentive to flip the
real-money flag for testing purposes disappears.

**The assertion is deliberately strict.** Only the `DU` prefix is accepted. IBKR issues
other non-live prefixes for advisor and institutional paper accounts; those are not
accepted until an operator actually needs one. A too-strict allowlist fails closed.

**The guard is still not a capital guarantee.** `interactive_brokers_paper` verifies the
account *identifier*, not the gateway it reaches. An operator who points `base_url` at a
gateway authenticated as a live user retains the ability to cause harm. This mitigates
the realistic failure mode (misconfigured account id, or reusing the live flag for
testing); it does not make misuse impossible.

**Follow-up work:**

- The socket/TWS path has no paper equivalent. It keeps requiring
  `live_trading_enabled`. Add `interactive_brokers_socket_paper` only if the socket path
  becomes the primary integration.
- `PaperBrokerAdapter` remains the default and remains a pure simulator. Any evaluation
  built on its fills is measuring an accounting identity, not execution. Books intended
  to produce operational evidence must move to `interactive_brokers_paper`.
- `scripts/checks/repo/live_safety_check.py` is unaffected: it blocks automation from
  setting `live_trading_enabled` to true/1, and nothing here does.
