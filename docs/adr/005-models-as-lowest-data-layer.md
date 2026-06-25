# ADR: models/ as the Lowest Data-Contract Layer

Type: adr
Status: Accepted
Created: 2026-06-25
Last Reviewed: 2026-06-25
Purpose: Record the decision to make src/trading/models/ the single home for all passive data contracts, organized into feature subfolders and importing nothing from higher layers.
Related: [Architecture Conventions](../architecture/architecture-conventions.md), [Trading Package Map](../maps/trading-package-map.md)

## Context

`models/` and `domain/` had no clear boundary. `models/` held persistence-shaped
contracts (`*Record`/`*Insert`/`*Config`), but `domain/` also held passive
dataclasses — `evaluation_models.py`, `promotion_models.py` (one even named
`PromotionReviewRecord`), plus value objects embedded in logic files
(`SleeveFillTransition`, the sleeve rotation value objects). A repository
(`repositories/promotion.py`) imported its data contracts from `domain/` while
every other repository used `models/`. The two packages also imported each other
(`models/rotation_config.py → domain.rotation`), so they were entangled peers
rather than cleanly layered.

`models/` was also a flat directory of ~19 single-class files.

## Decision

1. **All passive data contracts live in `models/`.** This includes
   `*Config`/`*Insert`/`*Record`, state/order models, and domain value objects
   (evaluation artifact + parts, promotion assessment/review, sleeve transition
   and rotation value objects).

2. **`models/` is the lowest layer.** It imports nothing from `domain`,
   `services`, `repositories`, `interfaces`, or `infrastructure`. `domain` may
   import `models`, never the reverse. Enforced by a `scripts/checks/layer_check.py`
   rule.

3. **`domain/` keeps logic + DI/behavioral contracts only** — pure functions plus
   contracts that hold callables or behavior (`BrokerConnection`,
   `FeatureFetcherSet`, `ExternalFeatureProvider`/`ExternalFeatureBundle`,
   `StrategySpec`). Moving those to `models/` would reintroduce `models → domain`
   imports.

4. **`models/` is organized into feature subfolders** (`accounts/`, `orders/`,
   `portfolio/`, `sleeves/`, `rotation/`, `strategy/`, `settings/`, `evaluation/`,
   `promotion/`), one contract per file. The package root re-exports the public
   types; the cluster subpackages (`evaluation/`, `promotion/`) also re-export
   from their `__init__`.

5. **Serialization that needs domain helpers stays out of the model.**
   `RotationConfig.to_db_dict()` returns the raw field→column mapping; the JSON
   encoding of its list columns is applied by `domain.rotation_config_to_db_dict`.

## Consequences

Benefits:

- A single, testable rule for where a data contract lives ("is it passive data?
  → `models/`").
- `models/` is a true foundation layer with an enforced no-upward-imports rule.
- The flat `models/` sprawl is resolved by feature subfolders.

Trade-offs / deferred:

- The policy-knob `*Settings` dataclasses (`EvaluationConfidenceSettings`,
  `PromotionPolicySettings`) stay in `domain/` for now because their field
  defaults are domain constants used by domain math. Relocating them — and
  finding a home for those constants — is deferred to a follow-up.
- A few domain value objects (sleeve transition/rotation results) now live apart
  from the pure functions that build them; the functions import them back from
  `models/`.
