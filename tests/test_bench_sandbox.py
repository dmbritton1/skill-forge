"""Tests for bench/sandbox.py. Run: python3 tests/test_bench_sandbox.py"""
import os
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "bench"))
import sandbox


def _paths(tmp):
    t = pathlib.Path(os.path.realpath(tmp))
    return t / "work", t / "work" / "clone-1", t / "work" / "plugin-abc", t / "dev", t / "home"


def test_profile_denies_the_three_roots_and_allows_the_exceptions():
    with tempfile.TemporaryDirectory() as tmp:
        work, dest, plugin, dev, home = _paths(tmp)
        text = sandbox.sandbox_profile(dest, plugin, work, dev, home=home)
        assert text.startswith("(version 1)\n(allow default)")
        assert text.count("(deny file-read-data file-write*") == 3
        for root in (dev, work, home / ".claude" / "projects"):
            assert '(require-all (subpath "%s")' % root in text, root
        assert '(require-not (subpath "%s"))' % dest in text
        assert '(require-not (subpath "%s"))' % plugin in text
        for suffix in ("", "-shm", "-wal", "-journal"):
            assert '(require-not (literal "%s.ledger.db%s"))' % (dest, suffix) in text
        assert '(require-not (subpath "%s"))' % sandbox.project_folder(dest, home) in text


def test_project_folder_matches_claude_codes_naming():
    home = pathlib.Path("/nonexistent-home")
    got = sandbox.project_folder(
        "/private/tmp/skillforge-bench/sf-author-verdict-from-treatment-d-learnnogate-3-3", home)
    assert got.endswith("/.claude/projects/"
                        "-private-tmp-skillforge-bench-sf-author-verdict-from-treatment-d-learnnogate-3-3")


def test_repo_parent_is_above_this_checkout():
    parent = sandbox.repo_parent(REPO)
    assert os.path.realpath(str(REPO)).startswith(parent + "/")
    assert parent != os.path.realpath(str(REPO))
    assert not os.path.realpath(str(REPO)).startswith(os.path.join(parent, ".claude"))


def test_a_quote_in_a_path_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        work, dest, plugin, dev, home = _paths(tmp)
        try:
            sandbox.sandbox_profile(pathlib.Path(str(dest) + '"x'), plugin, work, dev, home=home)
        except ValueError:
            return
        raise AssertionError("a quoted path was accepted")


def test_wrap_quotes_the_command_and_profile():
    got = sandbox.wrap("claude -p \"hi 'there'\"", "/w/a b.sb")
    assert got.startswith("sandbox-exec -f '/w/a b.sb' sh -c ")
    assert "hi" in got


def test_template_sha_is_stable_hex():
    assert len(sandbox.TEMPLATE_SHA) == 64 and int(sandbox.TEMPLATE_SHA, 16) >= 0


def test_self_check_passes_for_real():
    """Runs sandbox-exec for real; no claude session."""
    if not shutil.which("sandbox-exec"):
        print("SKIP sandbox-exec not present")
        return
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(os.path.realpath(tmp)) / "work"
        plugin = work / "plugin-test"
        (plugin / "scripts").mkdir(parents=True)
        (plugin / "scripts" / "validate.py").write_text("# stand-in\n", encoding="utf-8")
        assert sandbox.self_check(work, REPO, plugin) == []


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
