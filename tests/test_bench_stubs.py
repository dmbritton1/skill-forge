"""Tests for bench/stubs/_stub.py. Run: python3 tests/test_bench_stubs.py"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench" / "stubs"))
from _stub import stub_functions

MODULE = '''import os


def keeps_its_docstring(a, b=2):
    """First line.

      Odd   spacing   that must survive exactly.
    """
    return a + b


def has_no_docstring(scope, name):
    return os.path.join(scope, name)


def untouched():
    return "still here"
'''

NEW_DOC = '''    """Supplied contract.

    Second line.
    """
'''


def _stubbed(**kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "mod.py"
        p.write_text(MODULE, encoding="utf-8")
        stub_functions(p, ["keeps_its_docstring", "has_no_docstring"], **kwargs)
        return p.read_text(encoding="utf-8")


def test_existing_docstring_is_kept_byte_for_byte():
    out = _stubbed(docstrings={"has_no_docstring": NEW_DOC})
    assert '    """First line.\n\n      Odd   spacing   that must survive exactly.\n    """\n' in out
    assert "return a + b" not in out


def test_a_supplied_docstring_is_used_where_none_existed():
    out = _stubbed(docstrings={"has_no_docstring": NEW_DOC})
    assert NEW_DOC in out
    assert "os.path.join" not in out


def test_stubbed_functions_raise_and_the_rest_still_works():
    ns = {}
    exec(compile(_stubbed(docstrings={"has_no_docstring": NEW_DOC}), "mod.py", "exec"), ns)
    for name, args in (("keeps_its_docstring", (1,)), ("has_no_docstring", ("a", "b"))):
        try:
            ns[name](*args)
        except NotImplementedError:
            pass
        else:
            raise AssertionError("%s did not raise NotImplementedError" % name)
    assert ns["untouched"]() == "still here"
    assert ns["keeps_its_docstring"].__code__.co_varnames[:2] == ("a", "b")


def test_a_missing_function_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "mod.py"
        p.write_text(MODULE, encoding="utf-8")
        try:
            stub_functions(p, ["no_such_function"])
        except ValueError:
            pass
        else:
            raise AssertionError("a missing function must be refused")
        assert p.read_text(encoding="utf-8") == MODULE, "a refused stub must not write"


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
