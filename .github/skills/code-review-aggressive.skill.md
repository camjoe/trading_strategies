---
name: Code Review Aggressive
description: Deep, high-scrutiny review focused on defects, residual risk, stale code, and test adequacy with explicit zero-findings evidence.
---

Canonical definition: `.github/skills/code-review-aggressive/SKILL.md`

Use for:
- high-risk or safety-critical changes (broker adapters, live-trading guards, DB migrations, admin flows)
- pre-release reviews where explicit zero-findings evidence is required
- changes touching runtime jobs, schedulers, or account lifecycle flows

Prefer `code-review` for standard review work. Use `code-review-baseline` for lightweight quick checks.
