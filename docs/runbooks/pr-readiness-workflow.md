# PR Readiness Workflow

Type: runbook
Status: Active
Created: 2026-10-10
Last Reviewed: 2026-10-10
Purpose: Operate the GitHub workflow that runs `pr ready` on pull requests and keeps the readiness comment current.
Related: [Runbooks Index](README.md), [Check PR Readiness skill](../../.ai/skills/check-pr-readiness/SKILL.md), [Scripts Map](../maps/scripts-map.md)

`.github/workflows/pr-readiness.yml` runs the `pr ready` shortcut on every non-draft pull request into
`develop` and creates or edits the single `<!-- pr-readiness -->` comment. It is not a merge gate:
a failed run leaves the check red and posts nothing.

## How a pass runs

1. Checks out the pull request head and builds the repo-local `.venv`.
2. Reads the pull request, the previous readiness comment from `github-actions[bot]`, and CI state
   with `python -m scripts.forge review-context`, waiting for CI to settle (its own `readiness` check
   is excluded).
3. Runs the agent with the Claude token and **no GitHub token**. It writes the comment body to a file.
4. Refuses the body unless it starts with the marker and holds no runner path or credential-like text.
5. Posts it with `python -m scripts.forge comment-upsert`, which writes only the readiness comment.

Drafts, fork pull requests, and Dependabot pull requests are skipped.

## One-time setup

```bash
claude setup-token
gh secret set CLAUDE_CODE_OAUTH_TOKEN
```

The token draws on the Claude plan's usage limits. A leaked token is a credential in a public
repository's secrets; rotate it at expiry (one year) or on any suspicion.

## Repository variables

| Variable | Default | Effect |
|---|---|---|
| `READINESS_MAX_PASSES` | `8` | Stop reviewing a pull request after this many passes |
| `READINESS_CI_WAIT_SECONDS` | `1500` | How long a pass waits for CI before reviewing |
| `READINESS_SAVE_TRANSCRIPT` | unset | `true` uploads the scrubbed agent transcript as a 7-day artifact, to diagnose reviewer behavior |

```bash
gh variable set READINESS_SAVE_TRANSCRIPT --body true
```

## When a run fails

| Symptom | Cause |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN is not set` | The secret is missing |
| `The agent run reported an error` | Expired or rejected token, or the agent failed; read the step log |
| `did not write a comment body` | The agent finished without writing the body file; re-run |
| `contains a path or credential-like text` | The comment would have leaked a runner path or token; nothing was posted |
| `Readiness pass cap reached` (notice) | `READINESS_MAX_PASSES` passes already ran; raise the variable or review by hand |

Re-run a failed pass from the Actions tab, or push a commit. A newer push cancels an older pass.

## Pin and upgrade the agent

The workflow installs a pinned Claude Code version (`CLAUDE_CODE_VERSION` in the workflow). Upgrade it
deliberately and compare one pass before and after.
