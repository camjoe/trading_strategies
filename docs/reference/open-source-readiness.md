# Open-Source Readiness

Type: notes
Status: Active
Created: 2026-07-21
Last Reviewed: 2026-07-21
Purpose: Record the current public-source posture and the work intentionally deferred until the project adopts an open-source license.
Related: [Project Overview](../overview.md), [Architecture Conventions](../architecture/architecture-conventions.md), [Broker Integration](broker-integration.md), [Strategies](strategies.md)

## Purpose

This document keeps the publicly viewable repository moving toward open-source licensing without
prematurely granting reuse rights or extracting strategy code that is currently safe to keep in-tree.
It is the readiness checklist for maintainers preparing a future open-source release.

## Current posture

- The source repository is already publicly available on GitHub.
- The repository does not yet include a license. Until one is deliberately selected and added, the
  project is public source but must not describe itself as open source.
- The planned license is Apache License 2.0. Recording that plan does not apply the license or grant
  permission under it; the grant begins only when the license is deliberately added to the repository.
- Current strategy implementations are public and may remain in the repository. None are presently
  classified as private or release-blocking.
- The software is educational and research software, not financial advice or production-ready
  investment infrastructure.
- Broker integration, runtime automation, and live-trading paths require heightened safety review.

## Prepare continuously

Changes should avoid creating unnecessary work for eventual open-source licensing:

- Keep credentials, account identifiers, private datasets, generated databases, logs, and local
  operator configuration out of version control.
- Use generic examples in documentation rather than personal usernames, machine paths, account data,
  or deployment details.
- Keep strategy implementations behind the existing domain, catalog, and feature-provider boundaries.
  Shared execution, evaluation, persistence, and UI code must not depend on a specific private strategy.
- Treat tracked account profiles and strategy parameters as synthetic examples. Keep real strategy
  parameters, operator profiles, and research notes under the gitignored `local/strategies/` workspace.
  Private implementation code that must run with the application belongs in a separately distributed
  private package or repository, not in `local/`.
- Keep setup instructions reproducible from a clean checkout and use example configuration files for
  local secrets.
- Preserve clear safety gates around broker connections and order submission.
- Review new dependencies and copied assets for license compatibility and attribution requirements.

## Deferred decisions

These decisions should be made close enough to open-source licensing that they reflect the code and
release goals at that time:

### Apply the planned open-source license

The planned license is Apache License 2.0. Before applying it, confirm that the project still wants a
permissive license that allows commercial use and proprietary derivatives, and verify that the project
has the rights needed to license all included code, assets, datasets, and documentation. To apply it,
add the unmodified Apache License 2.0 text in a root `LICENSE` file and the `Apache-2.0` identifier to
package metadata. Do not add the license merely as a placeholder: doing so grants recipients the rights
in that license.

### Strategy separation

Before adopting the license, classify each strategy implementation and associated configuration,
documentation, fixtures, and history as either public example material or private intellectual
property. If private strategies exist, move them behind the established strategy interfaces into a
separately distributed package or private repository. Keep at least one non-sensitive example strategy
so a clean checkout can be evaluated end to end.

Removing a file from the current tree does not remove it from Git history. Because the repository is
already public, assume previously published strategy material may have been copied even if history is
later rewritten.

## Final open-source gate

Before adding a license or announcing the project as open source:

- [ ] Reconfirm and add the planned Apache License 2.0; update package metadata and README language.
- [ ] Complete an ownership and third-party-license review for code, assets, datasets, and docs.
- [ ] Classify strategies and separate anything private, including relevant Git history.
- [ ] Scan the full Git history for secrets, personal data, account data, and private deployment details.
- [ ] Verify clean-checkout setup and representative workflows on supported platforms.
- [ ] Run the full deterministic validation suite and a high-risk review of broker and live-trading paths.
- [ ] Confirm security-reporting contact details and supported-version expectations in `SECURITY.md`.
- [ ] Review public documentation for claims about profitability, safety, and production readiness.
- [ ] Confirm contribution, governance, release, and support expectations.

## Boundaries

This document records engineering and release preparation, not legal advice. License selection,
financial-service obligations, trademarks, privacy duties, and jurisdiction-specific requirements may
require qualified professional review before release.

## Related Docs

- [Architecture Conventions](../architecture/architecture-conventions.md)
- [Broker Integration](broker-integration.md)
- [Strategies](strategies.md)
- [Contributing](../../CONTRIBUTING.md)
- [Security Policy](../../SECURITY.md)
