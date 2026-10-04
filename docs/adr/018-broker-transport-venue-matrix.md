# ADR: Broker transport and venue are independent axes

Type: adr
Status: Accepted
Created: 2026-07-27
Last Reviewed: 2026-07-27
Purpose: Record why every IBKR transport supports both a paper and a live venue, expressed as a symmetric set of `broker_type` values, and why an unknown broker type now fails instead of falling through to the simulator.
Related: [ADR 017: IBKR paper broker type](017-ibkr-paper-broker-type.md), [Broker Integration](../reference/broker-integration.md), [IBKR Paper Trading Runbook](../runbooks/ibkr-paper-trading.md), [Architecture Conventions](../architecture/architecture-conventions.md)

## Context

[ADR 017](017-ibkr-paper-broker-type.md) added `interactive_brokers_paper` so that reaching an
IBKR paper account no longer required setting the real-money `live_trading_enabled` flag. It solved
the problem it set out to solve, but only for one transport. The resulting routing table was
asymmetric:

| | Web API | Socket/TWS |
|---|---|---|
| paper venue | `interactive_brokers_paper` | **missing** |
| live venue | `interactive_brokers_web` | `interactive_brokers` |

Two things are wrong with that shape.

**It conflates two independent axes.** *Transport* is how the runtime reaches IBKR — the Client
Portal Web API or the socket/TWS API. *Venue* is whether real money can move. Nothing about opening
a socket makes it inherently real-money; TWS and IB Gateway both expose paper ports (`7497`,
`4002`) precisely because paper trading over the socket is ordinary. Requiring
`live_trading_enabled` for the socket path was an artifact of how the code grew, not a property of
the transport.

**Venue was encoded two different ways.** On the web path it was a `broker_type` suffix; on both
live paths it was the `live_trading_enabled` column. A reader had to know which mechanism applied
where.

ADR 017 anticipated part of this, listing `interactive_brokers_socket_paper` as follow-up "only if
the socket path becomes the primary integration". That condition turned out to be the wrong test:
the asymmetry is a modelling defect regardless of which transport is primary.

Alternatives considered:

- **Transport in `broker_type`, venue inferred from the resolved account id.** Two values total
  (`_web`, `_socket`); a `DU` prefix means paper and needs no flag, anything else means live and
  requires one. Fewest strings, and `live_trading_enabled` regains exactly its stated meaning.
  Rejected for the same reason ADR 017 rejected prefix inference: the venue becomes implicit.
  Concretely, repointing a flag-enabled live book at a paper account would silently downgrade it
  from live to paper — the book keeps producing "live" evidence that is not live. The dangerous
  direction does fail closed, but the quiet direction corrupts the evidence trail.
- **Transport in `broker_type`, venue in a new `broker_venue` column.** Fully explicit on both axes
  with no combinatorial growth. Rejected on cost: it needs a migration, which cuts against the
  planned collapse of revisions `0001`–`0027` to a clean baseline, and ADR 017 already established
  that broker routing belongs in `broker_type`.

## Decision

Every IBKR transport gets both venues, named symmetrically:

| `broker_type` | Transport | Guard |
|---|---|---|
| `paper` (default) | none — in-process simulator | none; never leaves the process |
| `interactive_brokers_web` | Client Portal Web API | `live_trading_enabled = 1` |
| `interactive_brokers_web_paper` | Client Portal Web API | resolved account id must be a paper account |
| `interactive_brokers_socket` | socket/TWS | `live_trading_enabled = 1` |
| `interactive_brokers_socket_paper` | socket/TWS | resolved account id must be a paper account |

Consequences of the shape:

1. **`interactive_brokers_paper` is renamed to `interactive_brokers_web_paper`.** It named a venue
   without naming its transport, which stops working once both transports have one.
2. **`interactive_brokers` is renamed to `interactive_brokers_socket`, with no alias.** The rename
   was already documented as a deferred migration in `broker-integration.md`. No account row uses
   the value, so the compatibility shim would be dead code from birth.
3. **An unrecognized `broker_type` now raises `UnknownBrokerTypeError`.** Previously any unknown
   value fell through to `PaperBrokerAdapter`. That was tolerable while the names were stable; after
   a rename with no alias it is not, because the retired value would answer a broker request with
   fabricated simulator fills and no warning. `broker_type` that is absent or empty still defaults
   to `paper` — only a non-empty unrecognized value fails.

No migration is required: `accounts.broker_type` is `TEXT NOT NULL DEFAULT 'paper'` with no CHECK
constraint, and no account row currently uses any IBKR value.

### Where the paper assertion runs

The two transports learn their account identity at different times, and the guard follows:

- **Web API** — the account id comes from settings, so the assertion runs *before* connecting. A
  mismatch never opens a connection.
- **Socket** — IBKR reports account ids over the wire on connect, so the assertion can only run
  *after*. A mismatch connects, fails the assertion, and disconnects before returning.

Connecting is not trading, so the socket ordering still holds the guarantee that matters: no order
reaches a non-paper account. This required adding `managed_accounts()` to the `IbkrSocketClient`
protocol and both backends — `ib_async` exposes `IB.managedAccounts()`, and the native `ibapi`
client now captures the `managedAccounts` callback it was already receiving and discarding.

The socket assertion requires that *every* reported managed account is a paper account, and treats
an empty list as a failure. A socket session can trade any account it manages, so one live account
in the list is enough to make the session unsafe, and an empty list proves nothing.

## Consequences

**The real-money flag now means exactly one thing.** `live_trading_enabled` gates the two live
venues and nothing else. No operator has a reason to set it in order to test.

**Four IBKR values is the cost.** The matrix is transport × venue, so a third transport would mean
six. That is acceptable at two transports and is the price of keeping both axes explicit in one
column; if a third transport ever appears, revisit the rejected `broker_venue` column.

**Silent misconfiguration is largely closed off.** A typo in `broker_type` fails loudly. A paper
type pointed at a live account fails loudly. A live type without the flag fails loudly. The
remaining hole is unchanged from ADR 017: the assertion verifies the account *identifier*, not the
gateway it reaches.

**`scripts/checks/repo/live_safety_check.py` is unaffected** — it blocks automation from setting
`live_trading_enabled` to true/1, and nothing here does.
