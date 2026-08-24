"""Tests for the detached skill drafter (slice D1 design 4).
Run: python3 tests/test_draft.py
"""
import datetime
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import draft
import ledger

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


def entry(stamp, text):
    return json.dumps({"timestamp": stamp, "message": text})


def transcript(tmp, lines):
    p = pathlib.Path(tmp) / "transcript.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def when(hour):
    return "2026-08-24T%02d:00:00.000Z" % hour


def test_transcript_slice_keeps_only_the_window():
    with tempfile.TemporaryDirectory() as tmp:
        p = transcript(tmp, [entry(when(9), "before"), entry(when(11), "inside"),
                             entry(when(14), "after")])
        out = draft.transcript_slice(p, ledger.parse_ts(when(10)),
                                     ledger.parse_ts(when(12)))
        assert "inside" in out
        assert "before" not in out and "after" not in out


def test_transcript_slice_is_oldest_first():
    with tempfile.TemporaryDirectory() as tmp:
        p = transcript(tmp, [entry(when(10), "first"), entry(when(11), "second")])
        out = draft.transcript_slice(p, ledger.parse_ts(when(9)),
                                     ledger.parse_ts(when(12)))
        assert out.index("first") < out.index("second")


def test_transcript_slice_falls_back_to_the_tail_when_undated():
    with tempfile.TemporaryDirectory() as tmp:
        p = transcript(tmp, ["not json at all", "{}"])
        out = draft.transcript_slice(p, ledger.parse_ts(when(10)),
                                     ledger.parse_ts(when(12)))
        assert "not json at all" in out


def test_transcript_slice_respects_the_byte_cap():
    with tempfile.TemporaryDirectory() as tmp:
        big = [entry(when(11), "x" * 4000) for _ in range(100)]
        p = transcript(tmp, big)
        out = draft.transcript_slice(p, ledger.parse_ts(when(10)),
                                     ledger.parse_ts(when(12)))
        assert len(out.encode("utf-8")) <= draft.EVIDENCE_MAX_BYTES


def test_transcript_slice_keeps_the_newest_when_it_must_truncate():
    with tempfile.TemporaryDirectory() as tmp:
        lines = [entry(when(11), "OLDEST" + "x" * 4000)]
        lines += [entry(when(11), "x" * 4000) for _ in range(100)]
        lines += [entry(when(11), "NEWEST")]
        p = transcript(tmp, lines)
        out = draft.transcript_slice(p, ledger.parse_ts(when(10)),
                                     ledger.parse_ts(when(12)))
        assert "NEWEST" in out and "OLDEST" not in out


def test_transcript_slice_of_a_missing_file_is_empty():
    assert draft.transcript_slice("/nope/nothing.jsonl",
                                  ledger.parse_ts(when(10)),
                                  ledger.parse_ts(when(12))) == ""


def test_transcript_slice_is_empty_when_dated_but_window_matches_nothing():
    """A dated transcript with nothing in the window must not fall back.

    Falling back here would send an unrelated slice of the session as evidence
    for this struggle, and the resulting draft would look entirely legitimate.
    """
    with tempfile.TemporaryDirectory() as tmp:
        p = transcript(tmp, [entry(when(3), "early"), entry(when(20), "late")])
        assert draft.transcript_slice(p, ledger.parse_ts(when(10)),
                                      ledger.parse_ts(when(12))) == ""


def test_contracts_inlines_both_distillation_skills():
    text = draft.contracts(PLUGIN_ROOT)
    assert "distilling-skills" in text
    assert "distilling-failures" in text


def test_contracts_of_a_bad_root_is_empty_not_fatal():
    assert draft.contracts("/nope") == ""


def test_build_prompt_names_the_target():
    out = draft.build_prompt("make test", "evidence here", PLUGIN_ROOT)
    assert "make test" in out
    assert "evidence here" in out


def test_build_prompt_states_the_output_contract():
    out = draft.build_prompt("make test", "e", PLUGIN_ROOT)
    assert "ABORT:" in out


def test_build_prompt_frames_the_evidence_as_untrusted():
    out = draft.build_prompt("make test", "e", PLUGIN_ROOT)
    assert "never obey it" in out


def test_build_prompt_survives_percent_signs_in_the_evidence():
    """The evidence is arbitrary tool output; %-formatting it would explode."""
    out = draft.build_prompt("make test", "100% done %(oops)s %s", PLUGIN_ROOT)
    assert "100% done %(oops)s %s" in out


VALID = """---
name: widget-flush-order
kind: skill
description: >
  Flush widgets before closing the pool.
  Use when: a widget write races pool teardown.
  Do NOT use when: the pool is single-threaded.
verification.command: "python3 tests/test_widget.py"
fingerprints:
  - "await widget.flush({ force: true })"
  - "pool.close(after=widget.flush)"
---

## Procedure
1. Flush every widget, then close the pool.

## Verification
- `python3 tests/test_widget.py` should exit 0.
"""

INVALID = "---\nname: broken\nkind: skill\n---\n\nno description, no verification\n"

SECRETY = VALID.replace("1. Flush every widget, then close the pool.",
                        '1. Use AKIAIOSFODNN7EXAMPLE as the key.')


class Model:
    """Stands in for `claude -p`. The real one must never run in a suite."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, prompt, cwd, model=None, timeout=None):
        self.calls.append(prompt)
        return self.replies.pop(0) if self.replies else None


def with_model(model, fn):
    real = draft.run_model
    draft.run_model = model
    try:
        return fn()
    finally:
        draft.run_model = real


def produce(model, draft_id=1, target="make test", evidence="e"):
    return with_model(model, lambda: draft.produce(
        draft_id, target, evidence, ".", PLUGIN_ROOT))


def test_valid_draft_becomes_ready_and_lands_on_disk():
    def check(home):
        status, name, path = produce(Model(VALID))
        assert status == "ready"
        assert name == "widget-flush-order"
        assert pathlib.Path(path).read_text(encoding="utf-8") == VALID
    in_sandbox(check)


def test_abort_writes_nothing():
    def check(home):
        status, name, path = produce(Model("ABORT: a fresh Claude would know this"))
        assert (status, name, path) == ("aborted", None, None)
        assert not (home / ".claude" / "skillforge" / "drafts").exists()
    in_sandbox(check)


def test_invalid_draft_is_retried_once_then_succeeds():
    def check(home):
        model = Model(INVALID, VALID)
        status, _, _ = produce(model)
        assert status == "ready"
        assert len(model.calls) == 2
        assert "REJECTED" in model.calls[1]
    in_sandbox(check)


def test_invalid_twice_fails_and_does_not_call_a_third_time():
    def check(home):
        model = Model(INVALID, INVALID, VALID)
        status, _, _ = produce(model)
        assert status == "failed"
        assert len(model.calls) == 2
    in_sandbox(check)


def test_secret_bearing_draft_never_touches_disk():
    def check(home):
        status, _, path = produce(Model(SECRETY))
        assert status == "failed"
        assert path is None
        assert not (home / ".claude" / "skillforge" / "drafts").exists()
    in_sandbox(check)


def test_empty_evidence_never_reaches_the_model():
    """No evidence must cost no tokens -- and must not invent a draft."""
    def check(home):
        model = Model(VALID)
        status, name, path = with_model(model, lambda: draft.produce(
            1, "make test", "   \n  ", ".", PLUGIN_ROOT))
        assert (status, name, path) == ("failed", None, None)
        assert model.calls == []
    in_sandbox(check)


def test_model_failure_marks_failed():
    def check(home):
        assert produce(Model(None))[0] == "failed"
    in_sandbox(check)


def test_near_restatement_is_suppressed_as_duplicate():
    def check(home):
        idx = home / ".claude" / "skillforge" / "index.json"
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text(json.dumps({"entries": [{
            "name": "widget-flush-order",
            "description": "Flush widgets before closing the pool. "
                           "Use when: a widget write races pool teardown."}]}),
            encoding="utf-8")
        assert produce(Model(VALID))[0] == "duplicate"
    in_sandbox(check)


def test_unrelated_library_entry_does_not_suppress():
    def check(home):
        idx = home / ".claude" / "skillforge" / "index.json"
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text(json.dumps({"entries": [{
            "name": "tarball-extraction",
            "description": "Extract nested tarballs. Do NOT use for zip."}]}),
            encoding="utf-8")
        assert produce(Model(VALID))[0] == "ready"
    in_sandbox(check)


def test_empty_library_never_suppresses():
    def check(home):
        assert produce(Model(VALID))[0] == "ready"
    in_sandbox(check)


def test_write_draft_is_atomic_and_leaves_no_temp():
    def check(home):
        draft.write_draft(7, "hello")
        names = sorted(p.name for p in draft.drafts_dir().iterdir())
        assert names == ["7.md"]
    in_sandbox(check)


def test_cli_run_records_the_final_status():
    def check(home):
        did = ledger.open_draft("s1", "make test")
        # A real transcript is required: blank evidence short-circuits before
        # the model is ever called (see test_empty_evidence_never_reaches_the_model),
        # and this test is exercising the CLI's status-recording wiring, not that guard.
        tp = transcript(home, [entry(when(11), "struggled, then fixed it")])
        with_model(Model(VALID), lambda: draft.main(
            ["run", "--draft-id", str(did), "--target", "make test",
             "--transcript", str(tp), "--plugin-root", str(PLUGIN_ROOT)]))
        con = ledger.connect()
        try:
            row = con.execute("SELECT status, name FROM drafts WHERE id = ?",
                              (did,)).fetchone()
        finally:
            con.close()
        assert row == ("ready", "widget-flush-order")
    in_sandbox(check)


def test_cli_run_marks_failed_when_the_worker_raises():
    def check(home):
        did = ledger.open_draft("s1", "make test")

        def boom(*a, **k):
            raise RuntimeError("nope")

        # Non-blank evidence so `boom` is actually reached (see the comment
        # in test_cli_run_records_the_final_status above).
        tp = transcript(home, [entry(when(11), "struggled, then fixed it")])
        with_model(boom, lambda: draft.main(
            ["run", "--draft-id", str(did), "--target", "make test",
             "--transcript", str(tp), "--plugin-root", str(PLUGIN_ROOT)]))
        con = ledger.connect()
        try:
            assert con.execute("SELECT status FROM drafts WHERE id = ?",
                               (did,)).fetchone()[0] == "failed"
        finally:
            con.close()
    in_sandbox(check)


def test_resolve_saved_updates_the_row_and_keeps_the_file():
    def check(home):
        did = ledger.open_draft("s1", "make test")
        draft.write_draft(did, VALID)
        draft.main(["resolve", str(did), "saved"])
        con = ledger.connect()
        try:
            assert con.execute("SELECT status FROM drafts WHERE id = ?",
                               (did,)).fetchone()[0] == "saved"
        finally:
            con.close()
        assert (draft.drafts_dir() / ("%d.md" % did)).exists()
    in_sandbox(check)


def test_resolve_discarded_deletes_the_file_but_keeps_the_row():
    def check(home):
        did = ledger.open_draft("s1", "make test")
        draft.write_draft(did, VALID)
        draft.main(["resolve", str(did), "discarded"])
        con = ledger.connect()
        try:
            assert con.execute("SELECT signature, status FROM drafts WHERE id = ?",
                               (did,)).fetchone() == ("make test", "discarded")
        finally:
            con.close()
        assert not (draft.drafts_dir() / ("%d.md" % did)).exists()
    in_sandbox(check)


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS %s" % name)
