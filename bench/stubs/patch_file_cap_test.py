#!/usr/bin/env python3
"""Replace the file-cap grading test with a strategy-agnostic version.

The original decoys contained only ONE of the pattern's tokens, so the test
silently assumed the implementation narrows candidates by grepping a single
token. An implementation that greps every token (`git grep --all-match`)
narrows better, never hits the cap, finds the real match, and correctly
returns 1 -- and the original test marked that wrong.

The replacement removes the assumption:

  * every decoy contains ALL of the pattern's tokens, so any narrowing
    strategy returns them as candidates and the cap bites either way;
  * the decoys hold those tokens in REVERSE order, so patterns.matches()
    correctly refuses them (it requires in-order tokens within a window);
  * the genuine occurrence lives in a file that sorts last, beyond the cap.

So the fingerprint really IS present in the repo, and an implementation that
answers 0 is not merely unjustified -- it is factually wrong. Answering 1
would require reading past the stated cap. Only "unknown" is defensible.
"""
import re
import sys
from pathlib import Path

NEW_TEST = '''def test_snapshot_unknown_when_match_past_file_cap():
    def check(home):
        files = {}
        # Every decoy carries ALL the pattern's tokens, so any narrowing
        # strategy -- single-token grep or --all-match -- returns them and
        # the cap bites. Reversed order means patterns.matches() refuses
        # them, so none is a real hit.
        for i in range(retrieve.SNAPSHOT_MAX_FILES + 1):
            files["decoy%02d.js" % i] = "json application type raw express"
        # The genuine occurrence sorts last, so it is past the cap.
        files["zzz_real.js"] = "express.raw({type:'application/json'})"
        repo = git_repo(home, files)
        result = retrieve.fingerprint_preexisting(
            [["express", "raw", "type", "application", "json"]], str(repo))
        # It IS present, but not within the examined window: 0 would be
        # factually wrong and 1 would mean reading past the cap.
        assert result is None
    in_sandbox(check)
'''


def main():
    p = Path("tests/test_retrieve.py")
    src = p.read_text(encoding="utf-8")
    m = re.search(
        r"^def test_snapshot_unknown_when_match_past_file_cap\(\):\n(?:.*\n)*?(?=^def |\Z)",
        src, re.M)
    if not m:
        print("patch: file-cap test not found", file=sys.stderr)
        return 1
    p.write_text(src[:m.start()] + NEW_TEST + "\n" + src[m.end():], encoding="utf-8")
    if "SNAPSHOT_MAX_FILES + 1" not in p.read_text(encoding="utf-8"):
        print("patch: replacement did not take", file=sys.stderr)
        return 1
    print("patched file-cap test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
