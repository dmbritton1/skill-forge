"""Tests for bench/budget_sweep.py's pools. Run: python3 tests/test_bench_budget_sweep.py

budget_sweep reads relative paths at import, so every check runs in a subprocess
with a chosen cwd rather than importing it here.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEVEN = ["bench/distilled/A/learn-failure/1/SKILL.md", "bench/distilled/A/learn-failure/2/SKILL.md",
         "bench/distilled/A/learn-failure/3/SKILL.md", "bench/distilled/B/learn-nogate/1/SKILL.md",
         "bench/distilled/B/learn-nogate/2/SKILL.md", "bench/distilled/A/consolidated/1/SKILL.md",
         "bench/distilled/B/consolidated/1/SKILL.md"]
PROBE = ("import json, budget_sweep as bs; print(json.dumps({'ten': [e['_trap'] for e in bs.ten],"
         " 'seven': [e['_path'] for e in bs.seven]}))")


def _pools(cwd):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "scripts"), str(ROOT / "bench")]))
    r = subprocess.run([sys.executable, "-c", PROBE], cwd=str(cwd), env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_consolidated_seven_are_pinned():
    got = _pools(ROOT)
    assert got["seven"] == SEVEN
    assert set(got["ten"]) == {"A", "B"}


def test_a_later_trap_draft_does_not_join_the_pools():
    """E13 archives trap C's drafts beside A's and B's. §6.1 and §8 are defined over
    the consolidated seven, so a C draft must never enter them."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        (tmp / "bench" / "distilled").mkdir(parents=True)
        for trap in ("A", "B"):
            (tmp / "bench" / "distilled" / trap).symlink_to(ROOT / "bench" / "distilled" / trap)
        decoy = tmp / "bench" / "distilled" / "C" / "learn-nogate" / "1"
        decoy.mkdir(parents=True)
        shutil.copy(str(ROOT / SEVEN[0]), str(decoy / "SKILL.md"))
        (tmp / "bench" / "tasks.json").symlink_to(ROOT / "bench" / "tasks.json")
        got = _pools(tmp)
        assert set(got["ten"]) == {"A", "B"}, got["ten"]
        assert got["seven"] == SEVEN
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


if __name__ == "__main__":
    failures = 0
    for name in sorted(list(globals())):
        fn = globals()[name]
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS " + name)
            except Exception as err:
                failures += 1
                print("FAIL %s: %r" % (name, err))
    sys.exit(1 if failures else 0)
