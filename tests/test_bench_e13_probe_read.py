"""Tests for bench/e13_probe_read.py. Run: python3 tests/test_bench_e13_probe_read.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e13_probe_read as pr

TASK = "sf-author-verdict-from"
D1 = {"path": "bench/distilled/C/learn-nogate/1/SKILL.md", "name": "quote-rewrap"}
D2 = {"path": "bench/distilled/C/learn-failure-nogate/2/SKILL.md", "name": "byte-exact-quote"}


def ctl(resolved=False, ok=True, tail=None):
    return {"task": TASK, "arm": "control", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "injections": [], "skill_path": None}


def trt(d, resolved=False, delivered=True, ok=True):
    return {"task": TASK, "arm": "treatment", "resolved": resolved, "session_ok": ok,
            "session_tail": None, "skill_path": "~/x/wt/" + d["path"],
            "injections": [{"skill": d["name"]}] if delivered else [{"skill": "other"}]}


def full(d, resolved):
    return [trt(d, resolved=i < resolved) for i in range(3)]


def outcome_row(d, resolved=False, ok=True, tail=None):
    """A Stage 4 outcome row (spec section 8): same task/arm/skill_path as a
    probe treatment row, but installed with the consolidated seven (7
    extra_skills) and often archived plugin snapshot commits."""
    return {"task": TASK, "arm": "treatment", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "skill_path": "~/x/wt/" + d["path"],
            "injections": [{"skill": d["name"]}],
            "extra_skills": ["s%d" % i for i in range(7)],
            "env": {"plugin_commit": "archive:" + "a" * 40}}


def test_pooled_half_resolved_is_working():
    rows = [ctl()] * 3 + full(D1, 2) + full(D2, 1)
    res = pr.read_probe(rows, TASK, [D1, D2])
    assert res["batch"] == "complete" and res["pooled"] == [3, 6]
    assert res["verdict"] == "working"


def test_below_half_is_not_working():
    res = pr.read_probe([ctl()] * 3 + full(D1, 1) + full(D2, 1), TASK, [D1, D2])
    assert res["verdict"] == "not working"


def test_a_resolved_control_voids_the_batch():
    res = pr.read_probe([ctl(resolved=True), ctl(), ctl()] + full(D1, 3), TASK, [D1])
    assert res["batch"] == "void" and res["verdict"] is None


def test_a_session_limit_postpones_the_batch():
    rows = [ctl()] * 3 + full(D1, 1) + [ctl(ok=False, tail="You've hit your session limit")]
    res = pr.read_probe(rows, TASK, [D1])
    assert res["batch"] == "postponed" and res["cells"] == {}


def test_an_undelivered_row_does_not_count_and_two_void_the_cell():
    rows = [ctl()] * 3 + full(D1, 3) + [trt(D2, resolved=True, delivered=False)] + full(D2, 0)
    cell = pr.read_probe(rows, TASK, [D1, D2])["cells"][D2["path"]]
    assert cell["valid"] == 3 and cell["undelivered"] == 1 and cell["status"] == "complete"
    rows.append(trt(D2, resolved=True, delivered=False))
    res = pr.read_probe(rows, TASK, [D1, D2])
    assert res["cells"][D2["path"]]["status"] == "void"
    assert res["pooled"] == [3, 3] and res["verdict"] == "working"


def test_a_missing_cell_leaves_the_batch_incomplete():
    res = pr.read_probe([ctl()] * 3 + full(D1, 3), TASK, [D1, D2])
    assert res["batch"] == "incomplete" and res["verdict"] is None


def test_every_cell_void_is_not_working():
    rows = [ctl()] * 3 + [trt(D1, delivered=False)] * 2
    res = pr.read_probe(rows, TASK, [D1])
    assert res["batch"] == "complete" and res["verdict"] == "not working"


def test_outcome_rows_do_not_count_toward_the_probe():
    """A window read after Stage 4 sees outcome rows sharing task+arm+skill_path
    with the probe's treatment rows. They must not be counted as treatment runs,
    and an outcome-batch session-limit row must not postpone the probe."""
    clean = [ctl()] * 3 + full(D1, 2) + full(D2, 1)
    baseline = pr.read_probe(clean, TASK, [D1, D2])
    noisy = clean + [
        outcome_row(D1, resolved=True), outcome_row(D2, resolved=True),
        outcome_row(D1, ok=False, tail="You've hit your session limit"),
    ]
    assert pr.read_probe(noisy, TASK, [D1, D2]) == baseline


def test_a_fourth_delivered_run_does_not_count_toward_the_cell():
    rows = [ctl()] * 3 + [trt(D1, resolved=False)] * 3 + [trt(D1, resolved=True)]
    res = pr.read_probe(rows, TASK, [D1])
    cell = res["cells"][D1["path"]]
    assert cell["valid"] == 3 and cell["resolved"] == 0
    assert res["pooled"] == [0, 3] and res["verdict"] == "not working"


def sandboxed(r, verdict="clean"):
    """The row as written after the sandbox: a snapshot commit and an audit."""
    return dict(r, sandbox=True, audit={"verdict": verdict},
                env={"plugin_commit": "archive:" + "c" * 40})


def test_a_void_row_does_not_count_and_is_re_run():
    rows = [ctl()] * 3 + full(D1, 0) + [sandboxed(trt(D1, resolved=True), verdict="leak")]
    cell = pr.read_probe(rows, TASK, [D1])["cells"][D1["path"]]
    assert cell["valid"] == 3 and cell["resolved"] == 0
    assert cell["void"] == 1 and cell["rerun"] == 1


def test_a_void_control_that_resolved_does_not_void_the_batch():
    rows = [sandboxed(ctl(resolved=True), verdict="missing")] + [ctl()] * 3 + full(D1, 0)
    res = pr.read_probe(rows, TASK, [D1])
    assert res["batch"] == "complete" and res["control"]["void"] == 1


def test_a_sandboxed_snapshot_row_is_a_probe_row():
    rows = [sandboxed(ctl())] * 3 + [sandboxed(trt(D1, resolved=True))] * 3
    res = pr.read_probe(rows, TASK, [D1])
    assert res["pooled"] == [3, 3] and res["verdict"] == "working"


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
