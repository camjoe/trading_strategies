# Trading Package Map

## Purpose

Explain the top-level `trading/` structure as a **hybrid architecture**:

- A horizontal layered backbone for runtime application behavior.
- A few explicit bounded contexts kept top-level because they encapsulate unique workflows or external integrations.

## Top-Level Shape

### Layered Backbone

- `trading/interfaces/`: transport and operator entrypoints (`cli`, `runtime/jobs`, `runtime/data_ops`)
- `trading/services/`: orchestration/composition workflows
- `trading/repositories/`: SQL persistence adapters
- `trading/domain/`: side-effect-free policy/math/state-transition logic
- `trading/database/`: DB infrastructure/config/coercion
- `trading/models/`: shared passive data contracts (`*Config`, `*Insert`, `*Record`, state/order models)
- `trading/config/`: static file-backed configuration assets

### Bounded Contexts

- `trading/backtesting/`: a self-contained layered subsystem with its own `domain/services/repositories`
- `brokers/` (repo root): broker adapters and factory boundary (paper + live integrations); injected at the interface layer (`trading/interfaces/`); `trading/` must never import from `brokers/` except at the interface layer
- `trading/features/`: external-data feature-provider boundary for alternative strategies

## Placement Rules

- Use the layered backbone by default.
- Use top-level bounded contexts only when isolation materially improves clarity and safety.
- Keep `trading/models/` passive; move parsing/validation orchestration into services/domain helpers.
- Avoid adding facades that only forward imports unless they are deliberate public entrypoints.

## Related References

- [service-cookbook.md](service-cookbook.md) — task-oriented API reference ("what function do I call to do X?")
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- `docs/reference/adr-backtesting-layering.md`
