"""Say which groups of paths a pull request changed, for the ``changes`` job of the CI workflows.

``changed_scope.py <base> "<name>=<path> [<path> ...]" ...`` prints ``<name>=true`` or ``<name>=false`` for each group,
comparing the merge base of ``<base>`` and ``HEAD`` with ``HEAD``. A path is a file or a directory. A git error counts
as a change, so a failure runs the checks and never skips them.
"""

import subprocess
import sys


def changed(base: str, paths: list[str]) -> bool:
    """Whether ``HEAD`` differs from its merge base with *base* under *paths*; a git error also returns ``True``.

    ``git diff --quiet`` exits 1 when files differ and above 1 on an error, so any non-zero exit means "run the checks".
    """
    completed = subprocess.run(["git", "diff", "--quiet", f"{base}...HEAD", "--", *paths], check=False)
    return completed.returncode != 0


def main(argv: list[str]) -> int:
    """Print one ``<name>=true|false`` line per group in *argv*; exit status 2 for a missing base or a bad group."""
    if len(argv) < 2:
        print('usage: changed_scope.py <base> "<name>=<path> [<path> ...]" ...', file=sys.stderr)
        return 2
    base, *groups = argv
    results = []
    for group in groups:
        name, _, listed = group.partition("=")
        paths = listed.split()
        if not name or not paths:
            print(f"changed_scope: a group needs a name and at least one path: {group!r}", file=sys.stderr)
            return 2
        results.append(f"{name}={'true' if changed(base, paths) else 'false'}")
    print("\n".join(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
