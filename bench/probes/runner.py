#!/usr/bin/env python3
"""Shared harness for the graded probe suites (spec 2026-09-10 §3.1).

A probe suite scores ONE authored artifact. It imports that artifact from the
replayed clone's `scripts/` and nothing else -- never from the clone's
`tests/`, whose contents differ between the two base commits, and never from
this repo, which holds the finished implementation and would score every
artifact as perfect.
"""
import importlib
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile


def load(clone_root, module_name):
    """Import `module_name` from <clone_root>/scripts, evicting every cached clone module.

    Every clone names its modules the same thing. Without eviction the second
    artifact scored in a batch silently reuses the first one's module object,
    and the whole run grades one artifact many times.

    The eviction is deliberately broad -- ANY module already imported from a
    `scripts/` directory, not just `module_name`. detect.py imports patterns,
    ledger and retrieve, and retrieve is itself an authored artifact, so
    evicting only the named module would let a response_text clone pull the
    previous clone's retrieve. That is silent cross-contamination of exactly
    the kind the per-run ledger bug already cost this project a batch.
    """
    scripts = str(pathlib.Path(clone_root).resolve() / "scripts")
    sys.path.insert(0, scripts)
    try:
        for name in list(sys.modules):
            mod = sys.modules[name]
            path = getattr(mod, "__file__", None) or ""
            if name == module_name or os.sep + "scripts" + os.sep in path:
                del sys.modules[name]
        spec = importlib.util.spec_from_file_location(
            module_name, os.path.join(scripts, module_name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(scripts)


def in_sandbox(fn):
    """Run fn(tmpdir) with HOME and cwd redirected, then restore both.

    cwd is part of the sandbox, not just HOME: save_skill's --project-root
    defaults to ".", so anything that syncs treats the current directory as a
    project. Running unsandboxed once deleted a real project's hot skills.
    """
    old_home = os.environ["HOME"]
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        os.chdir(tmp)
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.chdir(old_cwd)
            os.environ["HOME"] = old_home


def git_repo(home, files):
    """A staged git repo under `home` containing `files` ({relpath: text})."""
    repo = pathlib.Path(home) / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    return repo


def main(namespace):
    """Run every test_* callable; print the repo's PASS/FAIL format.

    Returns the failure count. A probe that raises ANYTHING counts as failed:
    an artifact that raises TypeError is not partially correct.
    """
    failures = 0
    for name in sorted(namespace):
        fn = namespace[name]
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS " + name)
            except Exception as err:
                failures += 1
                print("FAIL %s: %r" % (name, err))
    return failures
