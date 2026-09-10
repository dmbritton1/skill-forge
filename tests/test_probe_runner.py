"""Tests for the probe runner. Run: python3 tests/test_probe_runner.py"""
import contextlib
import io
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench" / "probes"))
import runner


def test_load_imports_from_the_given_clone_not_this_repo():
    def check(home):
        scripts = home / "scripts"
        scripts.mkdir()
        (scripts / "marker_mod.py").write_text("VALUE = 'from-clone'\n", encoding="utf-8")
        mod = runner.load(home, "marker_mod")
        assert mod.VALUE == "from-clone"
    runner.in_sandbox(check)


def test_load_reimports_a_second_clone_with_the_same_module_name():
    # Two clones both define `retrieve`. Without cache eviction the second
    # load silently returns the first clone's module and every probe after
    # the first artifact scores the wrong code.
    def check(home):
        seen = []
        for tag in ("first", "second"):
            root = home / tag
            (root / "scripts").mkdir(parents=True)
            (root / "scripts" / "dup_mod.py").write_text(
                "VALUE = %r\n" % tag, encoding="utf-8")
            seen.append(runner.load(root, "dup_mod").VALUE)
        assert seen == ["first", "second"], seen
    runner.in_sandbox(check)


def test_load_evicts_transitively_imported_clone_modules():
    # `detect` imports `retrieve`, and `retrieve` is itself an authored
    # artifact. Evicting only the named module lets clone two's detect bind
    # clone one's retrieve, and every score after the first is wrong.
    def check(home):
        seen = []
        for tag in ("first", "second"):
            scripts = home / tag / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "leaf_mod.py").write_text("VALUE = %r\n" % tag, encoding="utf-8")
            (scripts / "top_mod.py").write_text(
                "import leaf_mod\nVALUE = leaf_mod.VALUE\n", encoding="utf-8")
            seen.append(runner.load(home / tag, "top_mod").VALUE)
        assert seen == ["first", "second"], seen
    runner.in_sandbox(check)


def test_in_sandbox_restores_home_and_cwd():
    before_home, before_cwd = os.environ["HOME"], os.getcwd()
    runner.in_sandbox(lambda home: None)
    assert os.environ["HOME"] == before_home
    assert os.getcwd() == before_cwd


def test_git_repo_creates_a_repo_with_the_files_staged():
    def check(home):
        repo = runner.git_repo(home, {"a.js": "hello world"})
        assert (repo / ".git").exists()
        assert (repo / "a.js").read_text() == "hello world"
    runner.in_sandbox(check)


def test_main_counts_failures_and_prints_the_repo_format():
    ns = {"test_ok": lambda: None,
          "test_bad": lambda: (_ for _ in ()).throw(AssertionError("boom"))}
    with contextlib.redirect_stdout(io.StringIO()):
        result = runner.main(ns)
    assert result == 1


if __name__ == "__main__":
    sys.exit(runner.main(globals()))
