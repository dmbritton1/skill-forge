"""Tests for E12's reader. Run: python3 tests/test_e12_read.py

The reader exists because the first read of E12 was wrong: an ad-hoc check
compared 6 resolved control sessions against a threshold written for 12 and
called the batch void. Spec 4.2 (clarified) evaluates control on a COMPLETE
cell; an unfinished cell is 4.3's business -- postponed, not void.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e12_read  # noqa: E402

E = "sf-escaping-breaks-symptom-match"
T = "sf-truncation-reports-absent"
R_SKILL = {E: "serialization-corrupts-matching", T: "lossy-transform-false-negative"}
I_SKILL = "arrow-tzinfo-string-trap"


def row(task, arm, resolved=True, ok=True, delivered=True):
    r = {"task": task, "arm": "control" if arm == "C" else "treatment",
         "resolved": resolved, "session_ok": ok}
    if arm != "C":
        stem = R_SKILL[task] if arm == "R" else I_SKILL
        r["skill_path"] = "~/x/bench/skills/%s.md" % stem
        r["injections"] = [{"skill": stem, "trigger": "prompt"}] if delivered else []
    return r


def cell(task, arm, resolved, n=6, **kw):
    """n valid rows, the first `resolved` of them resolved."""
    return [row(task, arm, resolved=i < resolved, **kw) for i in range(n)]


def full_batch(c_res=(6, 6), r_res=(6, 6), i_res=(6, 6)):
    rows = []
    for k, task in enumerate((E, T)):
        rows += cell(task, "R", r_res[k]) + cell(task, "I", i_res[k]) + cell(task, "C", c_res[k])
    return rows


def test_an_unmeasured_control_cell_is_incomplete_not_void():
    """The mistake this reader exists to prevent, as it happened: escaping
    control 6/6 valid, truncation control six refusals and nothing valid."""
    rows = cell(E, "C", 6) + [row(T, "C", resolved=False, ok=False) for _ in range(6)]
    v = e12_read.validity(rows)
    assert v["control"] == "incomplete", v
    assert v["control"] != "void"


def test_a_complete_control_below_ten_voids():
    v = e12_read.validity(full_batch(c_res=(5, 4)))
    assert v["control"] == "void", v


def test_a_complete_control_at_ten_holds():
    v = e12_read.validity(full_batch(c_res=(5, 5)))
    assert v["control"] == "holds", v


def test_a_treatment_row_whose_skill_never_arrived_is_flagged():
    rows = full_batch()
    rows.append(row(E, "I", delivered=False))
    v = e12_read.validity(rows)
    assert len(v["undelivered"]) == 1, v


def test_refused_rows_are_excluded_not_scored():
    rows = full_batch() + [row(T, "I", resolved=False, ok=False) for _ in range(3)]
    v = e12_read.validity(rows)
    assert v["control"] == "holds", v
    assert v["incomplete_cells"] == [], v


def test_criterion_harm_at_three_below_control():
    c = e12_read.criterion(full_batch(i_res=(5, 4)))
    assert c["I"]["verdict"] == "harm", c
    assert c["R"]["verdict"] == "no large harm", c


def test_criterion_is_ambiguous_between_the_two_bounds():
    c = e12_read.criterion(full_batch(i_res=(5, 5)))
    assert c["I"]["verdict"] == "ambiguous", c


def test_fisher_matches_the_figure_the_spec_pre_registered():
    """Spec section 7: '12/12 versus 8/12 is Fisher p ~ 0.09'."""
    p = e12_read.fisher(12, 12, 8, 12)
    assert abs(p - 0.0932) < 0.001, p


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
