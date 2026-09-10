#!/usr/bin/env python3
"""Graded probes for detect.response_text (spec §3.1).

Run: python3 bench/probes/probe_response_text.py <clone_root>

The stub states three clauses only -- a string may arrive, a structured
object may arrive, truncate to MAX_OUTPUT_CHARS -- and deliberately says
nothing about escaping or tokenization, because naming the hazard would hand
over the knowledge the benchmark measures. Probes 4-9 therefore come from
enumerating the input space, not from the contract.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runner

CLONE = None


def _detect():
    return runner.load(CLONE, "detect")


def _patterns():
    return runner.load(CLONE, "patterns")


def test_plain_string_under_the_cap_is_returned_unchanged():
    d = _detect()
    assert d.response_text("hello world") == "hello world"


def test_plain_string_over_the_cap_is_truncated():
    d = _detect()
    out = d.response_text("x" * (d.MAX_OUTPUT_CHARS + 500))
    assert len(out) == d.MAX_OUTPUT_CHARS


def test_flat_dict_yields_text_containing_its_values():
    d = _detect()
    out = d.response_text({"stdout": "connection refused"})
    assert "connection" in out and "refused" in out


def test_nested_dict_yields_text_containing_values_at_depth():
    d = _detect()
    out = d.response_text({"result": {"inner": {"msg": "connection refused"}}})
    assert "connection" in out and "refused" in out


def test_non_string_leaves_survive_into_the_text():
    d = _detect()
    out = d.response_text({"code": 500, "ok": False, "extra": None})
    assert "500" in out


def test_non_serializable_object_does_not_raise():
    d = _detect()

    class Opaque:
        pass

    out = d.response_text({"obj": Opaque()})
    assert isinstance(out, str)


def test_large_structure_never_exceeds_the_cap():
    d = _detect()
    out = d.response_text({"k%d" % i: "v" * 200 for i in range(5000)})
    assert len(out) <= d.MAX_OUTPUT_CHARS


def test_tokenize_recovers_a_flat_dict_value():
    d, p = _detect(), _patterns()
    out = d.response_text({"stderr": "Running webhook test...\nTypeError: bad operand"})
    hay = p.tokenize(out)
    assert p.matches(p.tokenize("TypeError bad operand"), hay), hay[:40]


def test_tokenize_recovers_a_nested_dict_value():
    d, p = _detect(), _patterns()
    out = d.response_text({"result": {"stderr": "Running webhook test...\nTypeError: bad operand"}})
    hay = p.tokenize(out)
    assert p.matches(p.tokenize("TypeError bad operand"), hay), hay[:40]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: probe_response_text.py <clone_root>", file=sys.stderr)
        sys.exit(2)
    CLONE = sys.argv[1]
    sys.exit(1 if runner.main(globals()) else 0)
