What goes in CONTRIBUTING.md?

A strong CONTRIBUTING.md typically answers:

How do I set up the project locally?
How do I run tests and linting?
What coding standards do we follow?
What is the expected workflow for changes?
How should pull requests be structured?
What should contributors avoid doing?

For a Python project, that usually includes environment setup, test commands, linting/formatting, migration workflow, commit/PR expectations, and links to deeper docs.

Example CONTRIBUTING.md for your setup
Development Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
Running Tests
pytest

Run a specific test file:

pytest tests/test_budget_requests.py
Linting & Formatting
ruff check .
ruff format .
Project Structure
‌

src/ - application code

‌

tests/ - test suite

‌

docs/ - architecture, conventions, maps, ADRs, and runbooks

Start here for architecture:

‌

docs/architecture/system-overview.md

Conventions

See:

‌

docs/conventions/python-style.md

‌

docs/conventions/testing.md

Making Changes
‌

Create or update tests.

‌

Run linting and formatting.

‌

Run the relevant test suite.

‌

Update documentation if behavior or architecture changes.

Database Changes
‌

Create migrations with Alembic.

‌

Do not edit existing migration files unless instructed.

Pull Requests

Include:

‌

Summary of changes

‌

Why the change was made

‌

Testing performed

‌

Any documentation updates

AI Agent Notes

AI assistants should read:

‌

AGENTS.md

‌

docs/maps/

‌

docs/conventions/

before making changes.

Why this matters for AI agents

A surprisingly large amount of AI failure comes from workflow mistakes, not coding mistakes:

Editing generated files manually

Forgetting migrations

Skipping tests

Violating layering conventions

Adding code in the wrong module

CONTRIBUTING.md gives the AI a procedural checklist that applies to every change.

It's especially useful because many AI tools automatically surface or prioritize files named:

README.md
CONTRIBUTING.md
AGENTS.md
CLAUDE.md

So you're putting instructions where tooling already expects them.

How it differs from AGENTS.md
CONTRIBUTING.md

Audience: humans first (and AI second). It explains the development process and contribution workflow.

AGENTS.md / CLAUDE.md

Audience: AI agents first. It explains how an AI should navigate and operate within the repository.

In practice, there is overlap. Many teams duplicate a small amount of information between them.

A good pattern is:

CONTRIBUTING.md = human contributor workflow.

AGENTS.md = concise AI onboarding + pointers to docs.

My recommendation for your project

Given the structure you're building, I would use:

README.md

Project overview, setup, and usage.

CONTRIBUTING.md

Development workflow, testing, linting, migrations, PR expectations, and links to conventions docs.

AGENTS.md

Short AI-specific entry point:

Read these docs first

Architecture summary

Important constraints

Common commands

Where domain maps live

docs/

The real long-term knowledge base.

This keeps responsibilities clear and avoids turning AGENTS.md into a giant duplicate of all documentation.

One subtle but important point

The best repositories treat CONTRIBUTING.md as operational policy, not a tutorial.

Avoid writing a 50-page onboarding manual there.

Keep it practical and enforceable:

Commands

Required checks

Workflow rules

Links to deeper docs

That makes it useful for both humans and AI agents.