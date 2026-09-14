#!/usr/bin/env python3
"""E13 trap E: blank save_skill.store_dir and native_dir so the model must author them.

Neither function had a docstring at the parent commit, and an author task needs
a contract, so this supplies one. That is a departure from the historical
condition (E13 spec, threat 2). Each docstring names the directory layout and
the base directory for each scope, and says nothing about resolving paths. The
historical bug (fixed in 06173b0) returned the project root unresolved, so a
relative "." never compared equal to the absolute home directory and re-saving
a skill from $HOME collided with itself.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import stub_functions

DOCSTRINGS = {
    "store_dir": '''    """Directory a saved skill of this kind and name is stored in.

    <base>/.claude/skillforge/skills/<name>, or .../antiskills/<name> for an
    antiskill, where <base> is `project_root` for project scope and the home
    directory for global scope.
    """
''',
    "native_dir": '''    """Directory the hot copy of a skill is materialized in.

    <base>/.claude/skills/skillforge-hot/<name>, with <base> chosen as in
    store_dir.
    """
''',
}


def main():
    try:
        stub_functions("scripts/save_skill.py", ["store_dir", "native_dir"], DOCSTRINGS)
    except ValueError as err:
        print("stub: %s" % err, file=sys.stderr)
        return 1
    print("stubbed store_dir, native_dir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
