#!/usr/bin/env python3
"""macOS sandbox for bench sessions.

docs/superpowers/specs/2026-09-14-bench-sandbox-audit-design.md, section 2.

Every bench session runs under `sandbox-exec` with a profile that denies the
operator's Developer tree, the other clones and hidden-test caches under WORK,
and other sessions' transcripts -- except this session's own clone, ledger,
transcript folder and plugin snapshot. It denies file CONTENT and writes, not
metadata: denying metadata on WORK breaks `cd` into a clone inside it
(verified 2026-09-14). The zero-session check:

    python3 bench/run.py --sandbox-check
"""
import hashlib
import os
import re
import shlex
import subprocess
from pathlib import Path

TEMPLATE = """(version 1)
(allow default)
(deny file-read-data file-write*
  (require-all (subpath "{repo_parent}")
               (require-not (subpath "{plugin}"))))
(deny file-read-data file-write*
  (require-all (subpath "{work}")
               (require-not (subpath "{dest}"))
               (require-not (subpath "{plugin}"))
               (require-not (literal "{dest}.ledger.db"))
               (require-not (literal "{dest}.ledger.db-shm"))
               (require-not (literal "{dest}.ledger.db-wal"))
               (require-not (literal "{dest}.ledger.db-journal"))))
(deny file-read-data file-write*
  (require-all (subpath "{projects}")
               (require-not (subpath "{project_folder}"))))
"""
# Recorded on every row as sandbox_profile: which rules ran, without the
# per-session paths.
TEMPLATE_SHA = hashlib.sha256(TEMPLATE.encode("utf-8")).hexdigest()


def _real(path):
    return os.path.realpath(str(path))


def repo_parent(repo_root):
    """The directory holding the main checkout.

    From git's common dir, so a worktree under .claude/worktrees/ resolves to
    its main checkout's parent, not to the worktrees directory -- the sandbox
    must hide every checkout and worktree, not just this one.
    """
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                         cwd=str(repo_root), capture_output=True, text=True, check=True)
    return _real(Path(out.stdout.strip()).parent.parent)


def project_folder(dest, home=None):
    """The ~/.claude/projects folder Claude Code writes this clone's transcript
    to: the real clone path with each non-alphanumeric character replaced by '-'."""
    home = Path(home) if home else Path.home()
    return os.path.join(_real(home / ".claude" / "projects"),
                        re.sub(r"[^A-Za-z0-9]", "-", _real(dest)))


def sandbox_profile(dest, plugin_dir, work, repo_parent_dir, home=None):
    home = Path(home) if home else Path.home()
    values = {"repo_parent": _real(repo_parent_dir), "plugin": _real(plugin_dir),
              "work": _real(work), "dest": _real(dest),
              "projects": _real(home / ".claude" / "projects"),
              "project_folder": project_folder(dest, home)}
    for v in values.values():
        if '"' in v or "\\" in v:
            raise ValueError("path cannot be quoted in a sandbox profile: %r" % v)
    return TEMPLATE.format(**values)


def write_profile(dest, plugin_dir, work, repo_root):
    """Write this session's profile beside its clone and return the path.

    It sits in WORK, which the profile denies; sandbox-exec reads the file
    before applying it, so that is safe.
    """
    path = Path(work) / (Path(dest).name + ".sb")
    path.write_text(sandbox_profile(dest, plugin_dir, work, repo_parent(repo_root)),
                    encoding="utf-8")
    return path


def wrap(cmd, profile_path):
    return "sandbox-exec -f %s sh -c %s" % (shlex.quote(str(profile_path)), shlex.quote(cmd))


def self_check(work, repo_root, plugin_dir):
    """Spec section 5.1, zero sessions: problems found, empty when the sandbox
    denies and allows what the spec says."""
    work = Path(work)
    dest, other = work / "sandbox-check", work / "sandbox-check-other"
    for d in (dest, other):
        d.mkdir(parents=True, exist_ok=True)
        (d / "probe.txt").write_text("probe\n", encoding="utf-8")
    # Real home, consistent with write_profile's own profile: the projects
    # deny (ruling 8) is otherwise never exercised by this check.
    other_project = Path.home() / ".claude" / "projects" / "-sandbox-check-other"
    other_project.mkdir(parents=True, exist_ok=True)
    (other_project / "probe.txt").write_text("probe\n", encoding="utf-8")
    profile = write_profile(dest, plugin_dir, work, repo_root)
    cases = [(Path(repo_root) / "bench" / "tasks.json", False),
             (other / "probe.txt", False),
             (dest / "probe.txt", True),
             (Path(plugin_dir) / "scripts" / "validate.py", True),
             (other_project / "probe.txt", False)]
    problems = []
    for path, readable in cases:
        if not path.is_file():
            # A missing file fails `cat` too, and would pass a deny case.
            problems.append("self-check file missing: %s" % path)
            continue
        r = subprocess.run(wrap("cat %s" % shlex.quote(str(path)), profile), shell=True,
                           capture_output=True, text=True, timeout=60)
        if (r.returncode == 0) != readable:
            problems.append("%s %s under the sandbox: %s"
                            % ("could not read" if readable else "could read", path,
                               (r.stderr or "").strip()[-200:]))
    return problems
