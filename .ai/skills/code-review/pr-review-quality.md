---
name: pr-review-quality
description: Reviews code quality in a PR diff — maintainability, single responsibility, modularity, and unnecessary complexity.
---

# PR Review — Quality

Scope: branch diff only. Focus on structural and design quality — not style, not architecture boundaries (those have their own passes).

## What to check

1. **Deterministic context** — use `review_scope_check` and `validate-code` output to avoid repeating scripted findings.
2. **Single responsibility** — does each function or class do one thing? Flag functions with multiple unrelated concerns or that are clearly doing too much.
3. **Modularity** — is new logic reusable or tightly coupled to one caller? Could it be extracted into a helper without effort?
4. **Unnecessary complexity** — is there a simpler approach? Look for nested conditionals that could be flattened, loops that could be comprehensions, or state management that could be stateless.
5. **New patterns** — is a new design pattern or abstraction introduced when an existing one would work? Flag it as a concern if no clear reason is evident.
6. **Readability** — would a reviewer unfamiliar with this area understand the intent in under 30 seconds? If not, the code likely needs restructuring or better naming.
7. **Test adequacy** — are new behavior paths and important edge cases covered? Do not rely only on whether a test file changed.

## Severity

- **BLOCKER** — the issue would make the code materially harder to maintain, extend, or debug (e.g., a 100-line function with no decomposition, untested critical path).
- **ADVISORY** — worth noting and considering; does not block merging.

## Output format

```
BLOCKER  | src/trading/services/foo.py:88 | Function handles 3 unrelated concerns; split into separate helpers
ADVISORY | src/trading/services/foo.py:120 | New `BaseProcessor` pattern not needed; `FooProcessor` could be a plain function
```

One line per finding. No findings → `Quality: Clean`.
