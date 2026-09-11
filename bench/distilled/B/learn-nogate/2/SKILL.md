---
name: truncated-scan-reports-unknown
kind: skill
scope: global
description: >
  A bounded evidence scan must return a three-state result, and every cap that
  stops it early (file count, byte window, probe budget) must return "unknown"
  instead of "not found".
  Use when: writing or fixing a search that stops at a limit -- first N matches,
  first N bytes of a file, a time/subprocess budget, a probe or API-call cap --
  and its answer feeds a decision, a metric, a ledger, or a cache.
  Do NOT use when: the scan is exhaustive with no cap, the caller only wants a
  boolean "found something" and never distinguishes absence, or the cap is a
  pure display limit such as pagination.
verification.command: "python3 tests/test_retrieve.py"
fingerprints:
  - "return None if unknown else 0"
  - "unknown = True  # candidates we never looked at could hold the match"
  - "if len(text) > SNAPSHOT_MAX_BYTES"
provenance:
  repo: /private/tmp/skillforge-bench/sf-truncation-reports-absent-distill-learn-nogate-2
  commit: 589f9da
  distilled: 2026-09-10
---

## Procedure
1. Find every cap in the scan. Read the function top to bottom and list each
   place the search can stop before it has looked everywhere: a slice such as
   `candidates[:MAX]`, a truncated read `text[:MAX_BYTES]`, a timeout, a
   retry/probe budget, an exception swallowed with `continue`. Caps hide in
   slices, so grep for `[:` and for every `MAX_`/`LIMIT_` constant.
2. Make the return type three-state: found (True/1), searched-everything-and-
   absent (False/0), and could-not-tell (`None`). Keep `None` distinct from
   `0` all the way to the storage column or the caller's branch. If the column
   is `NOT NULL` or the caller does `if result:`, fix that first, otherwise
   unknown collapses back into absent on arrival.
3. Add one `unknown` flag at the top of the scan. Set it at every cap site and
   at every swallowed error, then end with
   `return None if unknown else 0`.
4. Let a positive finding win over truncation. Return found immediately when
   the match is confirmed; a truncated scan that still found the thing is not
   unknown. Only the negative answer is weakened by a cap.
5. Short-circuit the caps you can detect before paying for them. If the input
   already exceeds the probe budget (more patterns than allowed probes), return
   unknown up front rather than probing a prefix and reporting a partial result
   as complete.
6. Detect truncation by comparing against the cap, not by hoping. Read the
   full value, then test `len(names) > MAX_FILES` and `len(text) > MAX_BYTES`;
   a slice looks identical whether or not it dropped anything, so the check has
   to happen before or beside the slice.
7. Write one test per cap that plants a real match strictly beyond the cap and
   asserts unknown. Sorting matters: name decoy files so the true match sorts
   last, and pad the byte test past the byte cap.

## Gotchas
- Returning `0` for "we stopped early" is the silent failure mode. It reads as
  evidence of absence and poisons whatever consumes it: a usage metric
  undercounts, a cache memoizes a wrong negative, a guard concludes the
  dangerous pattern is not present.
- `if not result:` treats `None` and `0` alike. Compare with `is None` at every
  consumer, and make sure the storage layer keeps NULL rather than coercing.
- A probe cap must be checked before the first probe if the test of correctness
  is "the cap short-circuited". Probing one pattern and finding a match returns
  found, which is indistinguishable from having ignored the cap.
- Swallowed `OSError` on an unreadable candidate is a cap too. The file might
  hold the match, so it sets unknown, not skip-and-call-it-absent.
- Truncation checks belong inside the per-candidate loop, after the match test.
  Putting the byte check first returns unknown for a file whose match sits in
  the first window.

## Verification
- `python3 tests/test_retrieve.py` exits 0 with every test PASS.
- When the procedure is NOT followed the command fails loudly. The three cap
  tests (`test_snapshot_unknown_when_match_past_file_cap`,
  `test_snapshot_unknown_when_match_past_byte_cap`,
  `test_snapshot_probe_cap_records_unknown`) report FAIL: an `AssertionError`
  where a truncated scan returned `0` instead of `None`, and an
  `AttributeError` where the probe-budget constant does not exist. The suite
  exits 1.
