# Commit Message Workflow

- When the user says they are ready to commit, asks for a commit message, or asks to summarize changes for commit, first run `python .\tools\project_manager\scripts\generate_commit_context.py`.
- Default to `--git-scope project-manager` unless the user explicitly asks for the whole workspace repository or for both scopes.
- Use newly archived items from `tools/project_manager/data/project_db.json` as the primary source for commit-message intent when present.
- If there are no newly archived items, fall back to current git changes since `HEAD`.
- Include documentation precheck findings from script output, and explicitly note any warning where non-doc files changed without corresponding docs updates.
- Return a short set of commit subject options and explain briefly which archived items or changed areas they came from.
- Always present each commit message option in its own fenced code block so the user can copy it directly.
- Do not create a commit automatically unless the user explicitly requests it.