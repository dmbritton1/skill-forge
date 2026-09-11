"""Environment isolation for the suite.

`bench/distill.py` sets SKILLFORGE_LEDGER, SKILLFORGE_FORCE_HOT and
SKILLFORGE_NO_CRITIQUE with a bare `os.environ[...] =` and never restores
them. That is correct for the bench driver, which is a throwaway process per
batch, and wrong inside pytest, which is one process for the whole suite: the
first test that exercises `distill.one` repoints `ledger.default_path()` at a
bench clone's ledger for every test that follows it.

The sandbox helpers in test_capture_e2e, test_sync and their siblings redirect
HOME and cwd, which looks like isolation and is not -- SKILLFORGE_LEDGER wins
over HOME by construction, so those tests read a real batch's drafts and
assert against them. Measured on 2026-09-10: 103 failures, every one of them
pollution and not a defect in the code under test. Running any of the affected
files alone passes, which is why this went unnoticed.

Restoring the whole environment per test fixes it at the only point every
test routes through, rather than teaching each sandbox helper a list of
variables it has to know about.
"""
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import sync

#: The genuine `sync._spawn_validation`, captured before pytest imports any
#: test module.
#:
#: Three test files replace it with an inert lambda at module scope, each so
#: that nothing in the file can launch a real detached `validate.py` -- a real
#: model turn and a real git worktree. That is correct, and none of them can
#: restore it, because the point is that it stays inert for the whole file.
#:
#: The collision is that tests/test_sync.py wants both: the inert stub for its
#: own tests, and the real function for _capture_popen_env, which stubs
#: subprocess.Popen and asserts on the env the real code builds. It captured
#: the real one on the line above its own stub -- which works only if it is
#: imported first. Alphabetically it is not: test_guard.py gets there first,
#: so test_sync.py captured test_guard's lambda, called it, and saw no Popen.
#: Two failures that appear only in a full-suite run and vanish in any subset.
#:
#: conftest is imported before every test module, so capturing here is the one
#: point that does not depend on collection order.
REAL_SPAWN_VALIDATION = sync._spawn_validation


@pytest.fixture(autouse=True)
def restore_environ():
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)
