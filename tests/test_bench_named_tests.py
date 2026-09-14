"""Tests for bench/run_named_tests.py. Run: python3 tests/test_bench_named_tests.py"""
import pathlib
import subprocess
import sys
import tempfile

RUNNER = pathlib.Path(__file__).resolve().parent.parent / "bench" / "run_named_tests.py"

SAMPLE = '''
import sys

def test_a_passes():
    pass

def test_b_fails():
    raise AssertionError("boom")

def test_c_exits():
    sys.exit(3)

def test_d_passes_after_failures():
    pass

def helper_not_a_test():
    raise RuntimeError("must never run")
'''


def _run(*args):
    with tempfile.TemporaryDirectory() as tmp:
        f = pathlib.Path(tmp) / "test_sample.py"
        f.write_text(SAMPLE, encoding="utf-8")
        r = subprocess.run([sys.executable, str(RUNNER), str(f)] + list(args),
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout.splitlines()


def test_every_test_runs_even_after_failures():
    rc, lines = _run()
    assert "PASS test_a_passes" in lines
    assert any(l.startswith("FAIL test_b_fails:") for l in lines)
    assert any(l.startswith("FAIL test_c_exits:") for l in lines), lines
    assert "PASS test_d_passes_after_failures" in lines, "an earlier failure aborted the run"
    assert not any("helper_not_a_test" in l for l in lines)
    assert rc == 1


def test_named_tests_run_only_those():
    rc, lines = _run("test_a_passes", "test_d_passes_after_failures")
    assert lines == ["PASS test_a_passes", "PASS test_d_passes_after_failures"], lines
    assert rc == 0


def test_a_missing_name_is_a_failure():
    rc, lines = _run("test_a_passes", "test_nope")
    assert "PASS test_a_passes" in lines
    assert any(l.startswith("FAIL test_nope:") for l in lines)
    assert rc == 1


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
