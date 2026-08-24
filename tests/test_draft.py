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


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS %s" % name)
