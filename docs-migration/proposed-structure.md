# Proposed Target Structure

Living document. This is the shape we are migrating toward. Annotations mark what is settled vs open.

**Legend:** ✅ decided · 🟡 proposed (not yet decided) · ❓ open question · ⚠️ risk to resolve before moving

> **Final layout = repo root (D-1, D-OPEN-1).** There is **no `agentswip/` folder** in the end state. `agentswip/` is a staging area; its contents are promoted to repo root and the old `docs/` is replaced. Read every `agentswip/…` path below as "repo-root `…`".

```
agentswip/                    📦 STAGING ONLY — contents promoted to repo root; folder then deleted
│                             (scaffold's own empty README/CONTRIBUTING/AGENTS/CLAUDE/copilot-instructions
│                              placeholders are dropped — real entrypoints live at repo root, see bottom)
├── docs/                     the knowledge source of truth (portable, tool-agnostic)
│   ├── architecture/         ✅ "how it works" (absorbs .github/BOT_ARCHITECTURE_CONVENTIONS.md)
│   ├── adr/                  ✅ "why" — split out of today's docs/reference/adr-*.md
│   ├── reference/            ✅ "what exists" — facts, schemas, endpoints, config, notes-*
│   │   ├── db-schema.md      ✅ generated schema block (describe_db_schema.py) + authored notes (D-9)
│   │   └── TEMPLATE.notes.md 🟡 keep TEMPLATE.* co-located (vs examples/ folder)
│   ├── business-rules/       ❓ finance/market/domain rules — seed with real content or omit (D-OPEN-5)
│   ├── runbooks/             ✅ "how to operate"
│   ├── conventions/          ✅ normative rules: style, naming, doc-header, bot-style
│   │                            (D-8 quality-gates.md + bot-authoring.md dropped as redundant;
│   │                             advisory-vs-enforced folded into validate-code skill)
│   ├── maps/                 "where things live"
│   │   ├── *.md              ✅ authored structural maps (file-lists + responsibilities); validated by scripts/checks/maps_check.py (D-OPEN-6)
│   │   └── domains/          🟡 authored maps: why things exist + which files matter (not auto-checked)
│   └── README.md             🟡 docs index (generated or maintained)
│
├── bots/                     ✅ authoritative home for agents/skills/workflows (D-OPEN-2)
│   ├── README.md             ✅ defines skill vs workflow vs agent + when-to-use which (D-8)
│   ├── agents/               ✅ merged — personas + agent defs in ONE folder (D-OPEN-3); prompts/ dropped
│   ├── skills/               ✅ authoritative; .github/skills/ becomes thin redirects
│   │   └── <skill>/SKILL.md
│   └── workflows/            🟡 multi-step procedures
│
└── scripts/
    └── generate_maps.py      🟡 build for real — deterministic map generation (D-OPEN-6)

# Repo-root entrypoints (D-OPEN-8):
README.md                     ✅ human front door — overview, setup, quick-start (stays as-is)
AGENTS.md                     ✅ CANONICAL AI entrypoint (single source of truth for agent rules/routing)
CLAUDE.md                     ✅ thin — `@AGENTS.md` import + Claude-only notes; links docs/README.md (no dup)
CONTRIBUTING.md               🟡 NEW — real human contributor workflow (to draft, staged)

# Tool-default locations keep THIN REDIRECT copies pointing at the authoritative source (D-OPEN-2, D-OPEN-8):
.github/copilot-instructions.md   🔁 thin redirect → AGENTS.md (Copilot is used)
.github/skills/                   🔁 thin references → bots/skills/

# Stays where GitHub mandates (out of scope for the move):
.github/workflows/*.yml       ✅ stays
.github/dependabot.yml        ✅ stays
```

## Folder definitions

| Folder | Answers | Test for "does it belong here?" |
|---|---|---|
| `architecture/` | How does this work? | Describes design/flow/boundaries of the running system |
| `adr/` | Why was it built this way? | Records a past decision + rationale; rarely changes |
| `reference/` | What exists? | Descriptive facts: schemas, endpoints, env vars, CLI, subsystem notes |
| `business-rules/` | What are the domain rules? | Finance/market/governance constraints, not code structure |
| `runbooks/` | How do I perform an operation? | Step-by-step procedure a human/agent follows |
| `conventions/` | What rules must I follow? | Normative ("you must"): style, naming, doc headers |
| `maps/` | Where do things live? | Inventory of files/dirs (structural) or domains (authored) |

## Dropped from the original scaffold

- ✅ `docs/examples/` and `bots/skills/examples/` folders — removed (D-OPEN-4). Worked examples embed in their governing doc; `TEMPLATE.*` blanks stay co-located.
- ✅ All scaffold `*-example.md` files (`*-example.md` in maps, conventions, adr, skills, workflows) — court-records illustrations of shape only; do not migrate.
