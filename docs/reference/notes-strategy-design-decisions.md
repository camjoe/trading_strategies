# Strategy Design Decisions

Recorded architectural and design decisions made during the initial strategy planning phase.

---

## Decisions
- Primary optimization target for the first version is highest total return. Supporting metrics should still be stored and displayed to avoid hiding fragile high-return strategies.
- Topic and politics strategies should start from free/public proxy data, not direct news NLP. The first implementation should be built so paid sentiment/news providers can be added later behind a provider interface.
- Scheduled strategy rotation is in scope for the first implementation. Regime-based rotation is deliberately excluded from the first wave to keep the control path simpler.
- “Full path including live hooks” is interpreted as designing reusable execution seams for future live trading, not implementing broker connectivity in this round.
- The first new strategy wave should favor strategies compatible with the current daily-close simulator before introducing intraday or options-history dependencies.

## Further Considerations
1. For “trending topics,” prefer theme/sector ETF rotation as the first concrete implementation because it is backtestable with existing market data patterns and does not require unreliable historical headline archives.
2. For “politics,” prefer macro and policy proxies with stable historical series in the first pass; direct event/news sentiment should be deferred until a durable provider and historical archive choice is made.
3. If you later want regime-based rotation, add it as a second-phase policy layer on top of the same strategy registry and rotation-state model rather than mixing it into the initial scheduled-rotation implementation.