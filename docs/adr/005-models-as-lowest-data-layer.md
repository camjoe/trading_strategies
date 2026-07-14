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
(the book fill-transition and rotation value objects). A repository
(`repositories/promotion.py`) imported its data contracts from `domain/` while
every other repository used `models/`. The two packages also imported each other
(`models/rotation_config.py → domain.rotation`), so they were entangled peers
rather than cleanly layered.

`models/` was also a flat directory of ~19 single-class files.

## Decision

1. **All passive data contracts live in `models/`.** This includes
   `*Config`/`*Insert`/`*Record`, state/order models, and domain value objects
   (evaluation artifact + parts, promotion assessment/review, book transition
   and rotation value objects).

2. **`models/` is the lowest layer.** It imports nothing from `domain`,
   `services`, `repositories`, `interfaces`, or `infrastructure`. `domain` may
   import `models`, never the reverse. Enforced by `scripts/checks/repo/layer_check.py`
   rule.

3. **`domain/` keeps logic + DI/behavioral contracts only** — pure functions plus
   contracts that hold callables or behavior (`BrokerConnection`,
   `FeatureFetcherSet`, `ExternalFeatureProvider`/`ExternalFeatureBundle`,
   `StrategySpec`). Moving those to `models/` would reintroduce `models → domain`
   imports.

4. **`models/` is organized into feature subfolders** (`accounts/`, `orders/`,
   `portfolio/`, `books/`, `rotation/`, `strategy/`, `settings/`, `evaluation/`,
   `promotion/`), one contract per file. The package root re-exports the public
   types; the cluster subpackages (`evaluation/`, `promotion/`) also re-export
   from their `__init__`.

5. **Serialization that needs domain helpers stays out of the model.**
   `RotationConfig.to_db_dict()` returns the raw field→column mapping; the JSON
   encoding of its list columns is applied by `domain.rotation_config_to_db_dict`.

6. **Constants follow the "lowest owning layer" rule.** A constant lives at the
   lowest layer that owns the concept *and* is reachable by all its consumers,
   without forcing an upward import. This sorts constants by their nature rather
   than dumping them in one place:
   - Generic, domain-agnostic primitives → `src/common/constants.py`.
   - A feature's data-contract vocabulary / schema metadata (allowed `status`
     values, artifact versions) → that feature's `constants.py` in `models/`
     (e.g. `models/promotion/constants.py`). `domain` policy then *reads* that
     vocabulary from `models/` — the correct direction.
   - Domain policy parameters (math weights, thresholds, gate messages) → the
     owning `domain/` module.
   - One-off values → top of the single file that uses them.

   Because these moved with their dataclasses, `models/{evaluation,promotion}/`
   gained `constants.py` files; that is intentional, not an accidental third tier.

## Consequences

Benefits:

- A single, testable rule for where a data contract lives ("is it passive data?
  → `models/`").
- `models/` is a true foundation layer with an enforced no-upward-imports rule.
- The flat `models/` sprawl is resolved by feature subfolders.

Resolved:

- The policy-knob `*Settings` dataclasses (`EvaluationConfidenceSettings`,
  `PromotionPolicySettings`) **stay in `domain/` — final, not deferred.** They are
  domain policy parameters (their fields default to domain math constants used by
  domain compute functions), not passive data contracts that cross a boundary.
  Forcing them and their math constants into `models/` to satisfy "all dataclasses
  in models" would put domain math in the data layer for no benefit. This is a
  deliberate, principled exception to decision (1): `models/` holds passive data
  contracts and their field vocabulary; domain policy config stays in `domain/`.

Trade-offs:

- A few domain value objects (book transition/rotation results) now live apart
  from the pure functions that build them; the functions import them back from
  `models/`.
