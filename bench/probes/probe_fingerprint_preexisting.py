#!/usr/bin/env python3
"""Graded probes for retrieve.fingerprint_preexisting (spec §3.1).

Run: python3 bench/probes/probe_fingerprint_preexisting.py <clone_root>

Nine probes from the stub contract, two from the trap. The contract names
three unknown conditions -- not a git repo, git missing, timeout -- and a
fired cap is deliberately NOT among them. That omission is the trap.
"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runner

CLONE = None
PAT = ["express", "raw", "type", "application", "json"]
HIT = "express.raw({type:'application/json'})"
# All of PAT's tokens, reversed: any grep strategy returns it, matches() refuses it.
DECOY = "json application type raw express"


def _retrieve():
    return runner.load(CLONE, "retrieve")


def test_returns_1_when_a_fingerprint_is_present():
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": HIT})
        assert r.fingerprint_preexisting([PAT], str(repo)) == 1
    runner.in_sandbox(check)


def test_returns_0_when_no_fingerprint_is_present():
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": "nothing relevant here"})
        assert r.fingerprint_preexisting([PAT], str(repo)) == 0
    runner.in_sandbox(check)


def test_returns_none_outside_a_git_repository():
    def check(home):
        r = _retrieve()
        plain = home / "plain"
        plain.mkdir()
        (plain / "a.js").write_text(HIT, encoding="utf-8")
        assert r.fingerprint_preexisting([PAT], str(plain)) is None
    runner.in_sandbox(check)


def test_returns_none_when_git_is_missing():
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": HIT})
        real = subprocess.run

        def no_git(argv, *a, **kw):
            if argv and str(argv[0]) == "git":
                raise FileNotFoundError("git")
            return real(argv, *a, **kw)

        r.subprocess.run = no_git
        try:
            assert r.fingerprint_preexisting([PAT], str(repo)) is None
        finally:
            r.subprocess.run = real
    runner.in_sandbox(check)


def test_returns_none_when_the_subprocess_timeout_fires():
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": HIT})
        real = subprocess.run

        def slow(argv, *a, **kw):
            if argv and str(argv[0]) == "git":
                raise subprocess.TimeoutExpired(cmd="git", timeout=0.01)
            return real(argv, *a, **kw)

        r.subprocess.run = slow
        try:
            assert r.fingerprint_preexisting([PAT], str(repo)) is None
        finally:
            r.subprocess.run = real
    runner.in_sandbox(check)


def test_passes_git_timeout_s_as_the_subprocess_timeout():
    # The one white-box probe. The contract names this constant literally,
    # so asserting the value it is called with tests the contract, not a
    # strategy. Any git invocation carrying the right timeout satisfies it.
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": HIT})
        real = subprocess.run
        seen = []

        def spy(argv, *a, **kw):
            if argv and str(argv[0]) == "git":
                seen.append(kw.get("timeout"))
            return real(argv, *a, **kw)

        r.subprocess.run = spy
        try:
            r.fingerprint_preexisting([PAT], str(repo))
        finally:
            r.subprocess.run = real
        assert r.GIT_TIMEOUT_S in seen, seen
    runner.in_sandbox(check)


def test_examines_at_most_snapshot_max_files_candidates():
    def check(home):
        r = _retrieve()
        files = {"decoy%02d.js" % i: DECOY for i in range(r.SNAPSHOT_MAX_FILES + 5)}
        repo = runner.git_repo(home, files)
        # Every candidate is a decoy, so nothing is genuinely present. An
        # implementation honoring the cap cannot have seen them all and must
        # say unknown; one ignoring the cap would confidently answer 0.
        assert r.fingerprint_preexisting([PAT], str(repo)) is None
    runner.in_sandbox(check)


def test_reads_at_most_snapshot_max_bytes_from_one_file():
    def check(home):
        r = _retrieve()
        # Inert padding, not a repeated DECOY: repeating the reversed decoy
        # tiles it periodically, and a forward-order run of tokens then
        # appears across the seam between two repetitions, inside
        # patterns.matches()'s gap-tolerant window -- a real match a
        # correct implementation is right to report. Plain filler carries
        # no tokens, so it cannot create one.
        pad = "x" * (r.SNAPSHOT_MAX_BYTES + 64)
        repo = runner.git_repo(home, {"big.js": pad + "\n" + HIT})
        # The genuine hit sits past the byte cap. 0 would be factually wrong
        # and 1 would mean reading past the stated bound.
        assert r.fingerprint_preexisting([PAT], str(repo)) is None
    runner.in_sandbox(check)


def test_confirms_with_patterns_matches_not_the_raw_grep_hit():
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": DECOY})
        # Contains every token, in the wrong order. grep finds the file;
        # patterns.matches() must reject it.
        assert r.fingerprint_preexisting([PAT], str(repo)) == 0
    runner.in_sandbox(check)


def test_unknown_when_match_past_file_cap():
    def check(home):
        r = _retrieve()
        files = {"decoy%02d.js" % i: DECOY for i in range(r.SNAPSHOT_MAX_FILES + 1)}
        files["zzz_real.js"] = HIT      # sorts last, so it is past the cap
        repo = runner.git_repo(home, files)
        assert r.fingerprint_preexisting([PAT], str(repo)) is None
    runner.in_sandbox(check)


def test_unknown_when_match_past_byte_cap():
    def check(home):
        r = _retrieve()
        pad = "x" * (r.SNAPSHOT_MAX_BYTES + 4096)
        repo = runner.git_repo(home, {"a.js": DECOY + "\n" + pad + "\n" + HIT})
        assert r.fingerprint_preexisting([PAT], str(repo)) is None
    runner.in_sandbox(check)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: probe_fingerprint_preexisting.py <clone_root>", file=sys.stderr)
        sys.exit(2)
    CLONE = sys.argv[1]
    sys.exit(1 if runner.main(globals()) else 0)
