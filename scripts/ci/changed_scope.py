"""Say which groups of paths a pull request changed, for the ``changes`` job of the CI workflows.

``changed_scope.py <base> "<name>=<path> [<path> ...]" ...`` prints ``<name>=true`` or ``<name>=false`` for each group,
comparing the merge base of ``<base>`` and ``HEAD`` with ``HEAD``. A path is a file or a directory. A git error counts
as a change, so a failure runs the checks and never skips them.
"""

import subprocess
import sys


def changed(base: str, paths: list[str]) -> bool:
    completed = subprocess.run(["git", "diff", "--quiet", f"{base}...HEAD", "--", *paths], check=False)
    return completed.returncode != 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('usage: changed_scope.py <base> "<name>=<path> [<path> ...]" ...', file=sys.stderr)
        return 2
    base, *groups = argv
    results = []
    for group in groups:
        name, _, paths = group.partition("=")
        if not name or not paths.split():
            print(f"changed_scope: a group needs a name and at least one path: {group!r}", file=sys.stderr)
            return 2
        results.append(f"{name}={'true' if changed(base, paths.split()) else 'false'}")
    print("\n".join(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
