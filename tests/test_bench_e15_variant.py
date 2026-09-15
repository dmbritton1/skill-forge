"""E15 spec section 1: the variant is the shipped distilling-skills at the spec
commit plus exactly three paragraphs. Run: python3 tests/test_bench_e15_variant.py"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC_COMMIT = "2719e97"
VARIANT = ROOT / "bench" / "variants" / "E15" / "distilling-skills.md"

RULE_GENERALIZE = """   **Name nothing a future session may not have.** Do not name tests, test
   files, fixtures or line numbers from this session. The session that uses
   the skill may be writing the code before any test exists, or may never see
   the test that caught the bug. Describe what the check verifies instead
   ("a request with no body must still get a 400 response")."""

RULE_ONE_SHOT = """   **Write the procedure for someone writing the code, not only fixing it.**
   The session that uses this skill may be implementing the function for the
   first time, with no broken version in front of it. Phrase each step as
   what the code must do ("return an empty list when there are no rows"),
   not as a search for the old mistake ("find the existing check and change
   it"). Do not start a step with "Find" unless the procedure is only ever
   about code that already exists."""

RULE_TRIGGERS = """   **Name the code, and the moment of writing it.** Put the function, class
   or API the skill is about in the description's first sentence, and make
   `Use when:` cover writing or editing that code, not only the moment it
   fails. A skill whose only trigger is a failure is never used by a session
   that has not failed yet."""

ANCHORS = (
    ('   "would a fresh Claude in a different repo benefit?"\n', RULE_GENERALIZE),
    ("   the procedure worked).\n", RULE_ONE_SHOT),
    ("   triggers fight over-injection; save_skill.py rejects drafts without them.\n", RULE_TRIGGERS),
)


def shipped_at_spec_commit():
    return subprocess.run(["git", "show", SPEC_COMMIT + ":skills/distilling-skills/SKILL.md"],
                          cwd=str(ROOT), capture_output=True, text=True, check=True).stdout


def test_variant_is_shipped_plus_exactly_three_paragraphs():
    expected = shipped_at_spec_commit()
    for anchor, rule in ANCHORS:
        assert expected.count(anchor) == 1, anchor
        expected = expected.replace(anchor, anchor + "\n" + rule + "\n")
    assert VARIANT.read_text(encoding="utf-8") == expected


def test_the_rules_carry_no_trap_c_vocabulary():
    for _, rule in ANCHORS:
        for word in ("verdict", "evidence", "quote", "wrap", "whitespace", "verbatim", "gate",
                     "normalis", "normaliz", "newline", "line break", "substring", "match"):
            assert word not in rule.lower(), (word, rule[:40])


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
