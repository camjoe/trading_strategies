# Open-Source Readiness

Type: notes
Status: Active
Created: 2026-07-21
Last Reviewed: 2026-07-21
Purpose: Track the remaining steps before the project adopts an open-source license.
Related: [Project Overview](../overview.md), [Strategies](strategies.md), [Contributing](../../CONTRIBUTING.md), [Security Policy](../../SECURITY.md)

## Purpose

This document tracks the work still required before the publicly viewable repository is licensed as
open source.

## Current posture

- The repository is public but has no license, so it is not yet open source.
- Apache License 2.0 is planned but has not been applied.
- Current strategies may remain public; private strategies are expected in the future.

## Final open-source gate

Before adding a license or announcing the project as open source:

- [ ] Add Apache License 2.0; update package metadata and README language.
- [ ] Complete an ownership and third-party-license review for code, assets, datasets, and docs.
- [ ] Move any strategies intended to remain private, including relevant Git history, out of the
  licensed repository.
- [ ] Verify a clean checkout can run representative workflows and passes the full validation suite.

## Notes

- Adding the license grants its rights; mentioning the plan does not.
- Private strategies that were previously committed may require Git-history remediation as well as
  removal from the current tree.
- This checklist is engineering guidance, not legal advice.

## Related Docs

- [Strategies](strategies.md)
- [Contributing](../../CONTRIBUTING.md)
- [Security Policy](../../SECURITY.md)
