"""Tests for bench/e15_read.py. Run: python3 tests/test_bench_e15_read.py"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
from fractions import Fraction

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e15_read as er

TASK = er.TASK
V = [{"group": "variant", "path": "bench/distilled/C/learn-e15-nogate/%d/SKILL.md" % i, "name": "v%d" % i}
     for i in (1, 2, 3, 4)]
B = [{"group": "baseline", "path": "bench/distilled/C/learn-nogate/%d/SKILL.md" % i, "name": "b%d" % i}
     for i in (1, 2, 3)]
DRAFTS = V + B


def ctl(resolved=False, ok=True, tail=None, audit="clean"):
    return {"task": TASK, "arm": "control", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "skill_path": None, "injections": [],
            "sandbox": True, "audit": {"verdict": audit}}


def trt(d, resolved=False, delivered=True, ok=True, audit="clean"):
    return {"task": TASK, "arm": "treatment", "resolved": resolved, "session_ok": ok,
            "session_tail": None, "skill_path": "~/x/wt/" + d["path"],
            "injections": [{"skill": d["name"] if delivered else "other"}],
            "sandbox": True, "audit": {"verdict": audit}}


def full(resolved):
    """Three valid runs per draft; `resolved` maps draft name to its count."""
    rows = []
    for d in DRAFTS:
        rows += [trt(d, resolved=i < resolved.get(d["name"], 0)) for i in range(3)]
    return rows


def test_order_interleaves_rotates_and_opens_each_round_with_a_control():
    o = er.order(DRAFTS)
    p = lambda d: d["path"]
    assert o[:8] == ["control", p(V[0]), p(B[0]), p(V[1]), p(B[1]), p(V[2]), p(B[2]), p(V[3])]
    assert o[8:16] == ["control", p(B[0]), p(V[1]), p(B[1]), p(V[2]), p(B[2]), p(V[3]), p(V[0])]
    assert o[16] == "control" and len(o) == 24
    assert o.count("control") == 3 and all(o.count(p(d)) == 3 for d in DRAFTS)


def test_probe_drafts_keeps_delivered_rows_variants_first():
    record = {"drafts": [
        {"group": "baseline", "path": "b1", "name": "b1", "delivered": True},
        {"group": "variant", "path": "v1", "name": "v1", "delivered": True},
        {"group": "variant", "path": "v2", "name": "v2", "delivered": False}]}
    assert [d["path"] for d in er.probe_drafts(record)] == ["v1", "b1"]


def test_draft_of_does_not_confuse_the_baseline_and_variant_segments():
    assert er.draft_of(trt(V[0]), DRAFTS) is V[0]
    assert er.draft_of(trt(B[0]), DRAFTS) is B[0]
    assert er.draft_of(ctl(), DRAFTS) is None


def test_bands():
    for d, v, reading in ((Fraction(2, 5), Fraction(1, 2), "the rules help"),
                          (Fraction(2, 5), Fraction(4, 9), "ambiguous"),
                          (Fraction(3, 20), Fraction(1, 2), "no large effect"),
                          (Fraction(-3, 20), Fraction(0), "no large effect"),
                          (Fraction(1, 5), Fraction(1, 2), "ambiguous"),
                          (Fraction(-39, 100), Fraction(0), "ambiguous"),
                          (Fraction(-2, 5), Fraction(0), "the rules hurt")):
        assert er.band(d, v) == reading, (d, v, reading)


def test_a_complete_batch_computes_v_b_and_d():
    res = er.read_batch([ctl()] * 3 + full({"v1": 3, "v2": 3, "v3": 2, "v4": 1, "b1": 1}), DRAFTS)
    m = res["measures"]
    assert res["batch"] == "complete"
    assert m["V"] == [9, 12] and m["B"] == [1, 9]
    assert m["d"] == 0.64 and m["reading"] == "the rules help"
    assert 0.0 <= m["p"] <= 1.0 and m["baseline_moved"] is False


def test_a_baseline_of_five_of_nine_is_flagged_as_moved():
    res = er.read_batch([ctl()] * 3 + full({"b1": 2, "b2": 2, "b3": 1}), DRAFTS)
    assert res["measures"]["baseline_moved"] is True


def test_a_resolved_valid_control_voids_the_batch():
    res = er.read_batch([ctl(resolved=True), ctl(), ctl()] + full({}), DRAFTS)
    assert res["batch"] == "void" and res["measures"] is None


LIMIT = "You've hit your session limit · resets 12:50am (America/New_York)\n"


def test_a_failed_last_session_pauses_an_unfinished_batch_and_never_counts():
    """Spec amendment 4: a session limit pauses the batch instead of postponing it."""
    rows = [ctl(), trt(V[0]), dict(trt(B[0], resolved=True, ok=False), session_tail=LIMIT)]
    res = er.read_batch(rows, DRAFTS)
    assert (res["batch"], res["reason"]) == ("paused", "session limit")
    assert res["drafts"][B[0]["path"]]["valid"] == 0
    assert er.read_batch(rows[:2] + [trt(B[0], ok=False)], DRAFTS)["reason"] == "failed session"
    weekly = dict(trt(B[0], ok=False), session_tail="You've hit your weekly limit · resets Mon")
    assert er.read_batch(rows[:2] + [weekly], DRAFTS)["reason"] == "session limit"
    assert er.read_batch(rows + [trt(B[0])], DRAFTS)["batch"] == "incomplete"
    done = [ctl()] * 3 + full({}) + [dict(ctl(ok=False), session_tail=LIMIT)]
    assert er.read_batch(done, DRAFTS)["batch"] == "complete"


def test_next_run_follows_the_order_and_reruns_a_failed_session_in_place():
    plan = er.order(DRAFTS)
    nxt = lambda rows: er.next_run(rows, DRAFTS, er.read_batch(rows, DRAFTS))
    run = lambda arm, **kw: ctl(**kw) if arm == "control" else trt(next(d for d in DRAFTS if d["path"] == arm), **kw)
    rows = []
    for i, arm in enumerate(plan):
        assert nxt(rows) == arm, i
        if i in (4, 17):  # cut off at the limit, then re-run in place after the reset
            rows.append(dict(run(arm, ok=False), session_tail=LIMIT))
            assert nxt(rows) == arm
        rows.append(run(arm))
    assert nxt(rows) is None and er.read_batch(rows, DRAFTS)["batch"] == "complete"


def test_repeats_after_the_order_are_capped_at_eight_finished_sessions():
    rows = [ctl()] * 3 + full({})
    rows = [trt(V[0], audit="leak") if (r.get("skill_path") or "").endswith(V[0]["path"]) else r for r in rows]
    nxt = lambda rows: er.next_run(rows, DRAFTS, er.read_batch(rows, DRAFTS))
    for _ in range(8):
        assert nxt(rows) == V[0]["path"]
        rows.append(trt(V[0], ok=False))           # a failed repeat does not use the budget
        assert nxt(rows) == V[0]["path"]
        rows.append(trt(V[0], audit="leak"))
    assert nxt(rows) is None and er.read_batch(rows, DRAFTS)["batch"] == "incomplete"


def test_rows_from_two_cli_versions_make_the_batch_unreadable():
    a = dict(ctl(), env={"cli": "2.1.266 (Claude Code)", "plugin_commit": "archive:x"})
    b = dict(ctl(), env={"cli": "2.1.267 (Claude Code)", "plugin_commit": "archive:x"})
    assert er.read_batch([a, a], DRAFTS)["batch"] == "incomplete"
    res = er.read_batch([a, b], DRAFTS)
    assert res["batch"] == "mixed" and er.next_run([a, b], DRAFTS, res) is None


def test_invalid_and_undelivered_rows_do_not_count():
    rows = [ctl()] * 3 + full({}) + [trt(V[0], resolved=True, audit="leak"),
                                    trt(V[0], resolved=True, ok=False),
                                    trt(V[0], resolved=True, delivered=False)]
    c = er.read_batch(rows, DRAFTS)["drafts"][V[0]["path"]]
    assert c["valid"] == 3 and c["resolved"] == 0 and c["invalid"] == 2 and c["undelivered"] == 1


def test_a_void_variant_draft_drops_out_of_v():
    rows = [ctl()] * 3 + full({"v1": 3}) + [trt(V[0], delivered=False)] * 2
    res = er.read_batch(rows, DRAFTS)
    assert res["drafts"][V[0]["path"]]["status"] == "void"
    assert res["batch"] == "complete" and res["measures"]["V"] == [0, 9]


def test_fewer_than_three_live_variant_drafts_means_d_is_not_computed():
    """Spec amendment 2: V may not rest on one or two drafts."""
    rows = ([ctl()] * 3 + full({"v1": 3, "v2": 3})
            + [trt(V[2], delivered=False)] * 2 + [trt(V[3], delivered=False)] * 2)
    res = er.read_batch(rows, DRAFTS)
    assert res["batch"] == "complete" and res["measures"] is None
    assert "fewer than 3 variant drafts" in res["reason"]


def test_a_void_baseline_draft_means_d_is_not_computed():
    rows = [ctl()] * 3 + full({}) + [trt(B[1], delivered=False)] * 2
    res = er.read_batch(rows, DRAFTS)
    assert res["batch"] == "complete" and res["measures"] is None and "baseline" in res["reason"]


def test_each_draft_counts_only_its_first_three_valid_runs():
    rows = [ctl()] * 3 + full({}) + [trt(V[1], resolved=True)]
    assert er.read_batch(rows, DRAFTS)["drafts"][V[1]["path"]]["resolved"] == 0


def test_missing_runs_leave_the_batch_incomplete_and_todo_names_them():
    rows = [ctl()] * 2 + [r for r in full({}) if er.draft_of(r, DRAFTS) is not B[2]] + [trt(B[2])] * 2
    res = er.read_batch(rows, DRAFTS)
    assert res["batch"] == "incomplete" and res["measures"] is None
    assert er.todo(res, DRAFTS) == ["control", B[2]["path"]]


def test_cli_order_and_window_requirement():
    with tempfile.TemporaryDirectory() as tmp:
        record = pathlib.Path(tmp) / "e15-probe.json"
        record.write_text(json.dumps({"drafts": [dict(d, delivered=True) for d in DRAFTS]}),
                          encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert er.main(["--order", "--record", str(record)]) == 0
        assert buf.getvalue().splitlines() == er.order(DRAFTS)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                er.main(["--record", str(record)])
        except SystemExit as exit_:
            assert exit_.code != 0
        else:
            raise AssertionError("--window was not required")


def test_cli_first_line_and_draft_lines():
    with tempfile.TemporaryDirectory() as tmp:
        record = pathlib.Path(tmp) / "e15-probe.json"
        record.write_text(json.dumps({"drafts": [dict(d, delivered=True) for d in DRAFTS]}),
                          encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            er.main(["--window", "2999-01-01T00:00:00", "-", "--record", str(record)])
        lines = buf.getvalue().splitlines()
        assert lines[0].startswith("batch: incomplete")
        assert sum(1 for l in lines if l.startswith("  variant ")) == 4
        assert sum(1 for l in lines if l.startswith("  baseline ")) == 3


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
