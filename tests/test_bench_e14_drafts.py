"""E14 spec section 2: the four drafts differ only in trigger and kind.
Run: python3 tests/test_bench_e14_drafts.py"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import save_skill

CELLS = ("sf", "sw", "af", "aw")
USE = {
    "f": "Use when: a verbatim-quote evidence gate fails a quote that differs from "
         "the source text only by line breaks or indentation.",
    "w": "Use when: writing or editing a gate that checks model-quoted evidence "
         "against source text with a substring test, e.g. `evidence in text`.",
}
FIX = ('ev = " ".join((f.get("evidence") or "").split()) '
       'if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()): '
       'return "fail"')
NAIVE = ('ev = (f.get("evidence") or "").strip()', "ev not in text")
FRAMING = "looks like the strictest, safest"


def flat(s):
    return " ".join(s.split())


def text(cell):
    return (ROOT / "bench" / "drafts" / "E14" / ("e14-quote-gate-rewrap-%s.md" % cell)).read_text(
        encoding="utf-8")


def test_every_draft_saves_cleanly():
    for c in CELLS:
        assert save_skill.validate(text(c)) == [], (c, save_skill.validate(text(c)))


def test_name_and_kind_match_the_cell():
    for c in CELLS:
        fm, _ = save_skill.parse_frontmatter(text(c))
        assert fm["name"] == "e14-quote-gate-rewrap-" + c
        assert fm["kind"] == ("skill" if c[0] == "s" else "antiskill")


def test_the_use_when_line_is_the_cells_trigger_and_nothing_else_differs_in_description():
    rest = set()
    for c in CELLS:
        fm, _ = save_skill.parse_frontmatter(text(c))
        desc = flat(fm["description"])
        assert desc.count("Use when:") == 1, c
        assert flat(USE[c[1]]) in desc, c
        rest.add(desc.replace(flat(USE[c[1]]), ""))
    assert len(rest) == 1, rest


def test_fingerprints_are_identical():
    fps = {repr(save_skill.parse_frontmatter(text(c))[0].get("fingerprints")) for c in CELLS}
    assert len(fps) == 1 and "None" not in fps, fps


def test_same_kind_drafts_have_identical_bodies():
    body = lambda c: save_skill.parse_frontmatter(text(c))[1]
    assert body("sf") == body("sw")
    assert body("af") == body("aw")


def test_every_draft_carries_the_fix_and_the_naive_check():
    for c in CELLS:
        t = flat(text(c))
        assert FIX in t, c
        for piece in NAIVE:
            assert piece in t, (c, piece)


def test_only_anti_skills_carry_the_trap_framing():
    for c in CELLS:
        assert (FRAMING in flat(text(c))) == (c[0] == "a"), c


def test_no_draft_names_a_hidden_test():
    for c in CELLS:
        assert set(re.findall(r"test_[a-z_]+", text(c))) <= {"test_validate"}, c


def test_lengths_are_within_ten_percent():
    lens = [len(text(c)) for c in CELLS]
    assert min(lens) >= 0.9 * max(lens), lens


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
