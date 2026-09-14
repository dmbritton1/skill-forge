#!/usr/bin/env python3
"""Run a stdlib-style test file one test at a time, catching each failure.

    python3 bench/run_named_tests.py tests/test_x.py [test_name ...]

Prints `PASS <name>` or `FAIL <name>: <error>` per test, which is the format
bench/run.py::score counts. With no names, runs every `test_*` function in
sorted order. Exits 1 if any test failed or a named test does not exist.

Exists because some of this repo's test files abort at their first failure
(tests/test_draft.py's runner has no try/except), and score() counts a test it
never sees as failed, so one early failure would zero every later graded test.
SystemExit is caught too: tests that drive a main() can raise it.
"""
import importlib.util
import pathlib
import sys


def load(path):
    path = pathlib.Path(path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def run(module, names=None):
    tests = sorted(n for n, v in vars(module).items()
                   if n.startswith("test_") and callable(v))
    failures = 0
    for name in (names or tests):
        fn = getattr(module, name, None)
        if not name.startswith("test_") or not callable(fn):
            print("FAIL %s: no such test" % name)
            failures += 1
            continue
        try:
            fn()
            print("PASS %s" % name)
        except (Exception, SystemExit) as err:
            failures += 1
            print("FAIL %s: %r" % (name, err))
    return failures


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    return 1 if run(load(argv[0]), argv[1:]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
