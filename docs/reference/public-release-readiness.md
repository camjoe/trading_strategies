# Public Release Readiness

Type: notes
Status: Active
Created: 2026-07-21
Last Reviewed: 2026-07-21
Purpose: Record the current public-release posture and the work intentionally deferred until the project approaches open-source publication.
Related: [Project Overview](../overview.md), [Architecture Conventions](../architecture/architecture-conventions.md), [Broker Integration](broker-integration.md), [Strategies](strategies.md)

## Purpose

This document keeps the repository moving toward open-source availability without prematurely granting
reuse rights or extracting strategy code that is currently safe to keep in-tree. It is the readiness
checklist for maintainers preparing a future public release.

## Current posture

- The project is being prepared for a future open-source release.
- The repository does not yet include a license. Until one is deliberately selected and added, the
  project must not describe itself as open source.
- Current strategy implementations may remain in the repository. None are presently classified as
  private or release-blocking.
- The software is educational and research software, not financial advice or production-ready
  investment infrastructure.
- Broker integration, runtime automation, and live-trading paths require heightened safety review even
  when the surrounding code is publicly available.

## Prepare continuously

Changes should avoid creating unnecessary work for the eventual release:

- Keep credentials, account identifiers, private datasets, generated databases, logs, and local
  operator configuration out of version control.
- Use generic examples in documentation rather than personal usernames, machine paths, account data,
  or deployment details.
- Keep strategy implementations behind the existing domain, catalog, and feature-provider boundaries.
  Shared execution, evaluation, persistence, and UI code must not depend on a specific private strategy.
- Keep setup instructions reproducible from a clean checkout and use example configuration files for
  local secrets.
- Preserve clear safety gates around broker connections and order submission.
- Review new dependencies and copied assets for license compatibility and attribution requirements.

## Deferred release decisions

These decisions should be made close enough to publication that they reflect the code and release
goals at that time:

### Open-source license

Select an OSI-approved license and add its unmodified text in a root `LICENSE` file. Then add the
license identifier to package metadata and verify that dependency, asset, and documentation licenses
are compatible. Do not add a license merely as a placeholder: doing so grants recipients the rights in
that license.

### Strategy separation

Before publication, classify each strategy implementation and associated configuration, documentation,
fixtures, and history as either public example material or private intellectual property. If private
strategies exist, move them behind the established strategy interfaces into a separately distributed
package or private repository. Keep at least one non-sensitive example strategy so a clean checkout can
be evaluated end to end.

Removing a file from the current tree does not remove it from Git history. Decide whether any prior
strategy material requires history rewriting before making the repository public.

## Final public-release gate

Before changing repository visibility or announcing an open-source release:

- [ ] Choose and add the license; update package metadata and README language.
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
