"""Tests for the shared pattern matcher (slice C1 design §2). Run: python3 tests/test_patterns.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import patterns


def test_tokenize_ignores_formatting():
    a = patterns.tokenize("express.raw({type: 'application/json'})")
    b = patterns.tokenize('express.raw({ type: "application/json" })')
    assert a == b
    assert a == ["express", "raw", "type", "application", "json"]


def test_tokenize_keeps_short_and_numeric_tokens():
    # unlike retrieve.tokenize (BM25 prose), code and error text need these
    assert patterns.tokenize("HTTP 500 id x") == ["http", "500", "id", "x"]


def test_tokenize_splits_camel_and_symbols_consistently():
    assert patterns.tokenize("StripeSignatureVerificationError: no signatures found") == [
        "stripesignatureverificationerror", "no", "signatures", "found"]


def test_matches_exact_sequence():
    pat = patterns.tokenize("npx stripe trigger")
    assert patterns.matches(pat, patterns.tokenize("npx stripe trigger payment_intent.succeeded"))


def test_matches_tolerates_inserted_tokens():
    pat = patterns.tokenize("npx stripe trigger")
    hay = patterns.tokenize("npx stripe --api-key sk_test_x trigger payment_intent.succeeded")
    assert patterns.matches(pat, hay)


def test_window_rejects_distant_tokens():
    pat = patterns.tokenize("stripe signature")
    hay = ["stripe"] + ["filler"] * 100 + ["signature"]
    assert patterns.matches(pat, hay) is False


def test_window_size_formula():
    assert patterns.window(["a", "b"]) == 3 * 2 + 8


def test_order_matters():
    pat = patterns.tokenize("signature stripe")
    assert patterns.matches(pat, patterns.tokenize("stripe signature verification")) is False


def test_empty_pattern_never_matches():
    assert patterns.matches([], patterns.tokenize("anything at all")) is False
    assert patterns.matches([], []) is False


def test_single_token_pattern():
    pat = patterns.tokenize("stripesignatureverificationerror")
    assert patterns.matches(pat, patterns.tokenize("caught StripeSignatureVerificationError here"))
    assert patterns.matches(pat, patterns.tokenize("nothing relevant")) is False


def test_repeated_first_token_still_matches():
    # first occurrence is too far from the rest; a later one is in range
    pat = patterns.tokenize("alpha beta")
    hay = ["alpha"] + ["x"] * 50 + ["alpha", "beta"]
    assert patterns.matches(pat, hay)


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
