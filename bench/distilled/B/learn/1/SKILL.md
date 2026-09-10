---
name: capped-scan-reports-unknown-not-absent
kind: skill
scope: project
description: >
  Every cap in a bounded repo scan must widen the result to unknown (None), never
  let it collapse to absent (0), and the cap must be detected before the slice that
  destroys the evidence.
  Use when: writing or changing a bounded search whose answer feeds the ledger --
  fingerprint_preexisting in retrieve.py, symptom or verification matching in
  detect.py, or any new probe that caps candidate files, bytes read, or probe count.
  Do NOT use when: the search is unbounded, the caller only needs a boolean and no
  event row is written, or you are tuning the cap constants themselves rather than
  the reporting of a cap hit.
verification.command: "python3 tests/test_retrieve.py"
fingerprints:
  - "if len(names) > SNAPSHOT_MAX_FILES:"
  - "if len(text) > SNAPSHOT_MAX_BYTES:"
  - "if len(probes) > SNAPSHOT_MAX_PROBES:"
provenance:
  repo: /private/tmp/skillforge-bench/sf-truncation-reports-absent-distill-learn-1
  commit: 589f9da
  distilled: 2026-09-09
---

## Procedure

1. List every cap the scan enforces before writing it. In `fingerprint_preexisting`
   there are four, not one: the subprocess timeout, the probe count
   (`SNAPSHOT_MAX_PROBES`), the candidate-file count (`SNAPSHOT_MAX_FILES`), and the
   bytes read per file (`SNAPSHOT_MAX_BYTES`). A cap you did not enumerate is a cap
   whose truncation you will report as `0`.
2. Carry one `unknown = False` flag through the whole scan and set it at every one
   of those boundaries. Return `None if unknown else 0` at the end. Only a positive
   match may return early, because presence is the one conclusion a partial sweep
   can actually support.
3. Detect each cap hit **before** the operation that discards the evidence. After
   `names[:SNAPSHOT_MAX_FILES]` and `text[:SNAPSHOT_MAX_BYTES]` there is nothing
   left to tell you it was truncated, so compare the full length first:
   `if len(names) > SNAPSHOT_MAX_FILES: unknown = True`.
4. Short-circuit a budget you cannot afford to spend, rather than spending part of
   it. If the probe list is longer than `SNAPSHOT_MAX_PROBES`, return `None`
   immediately without running any `git grep`. Probing the first few and reporting
   what they found makes the answer depend on fingerprint ordering, which no caller
   controls.
5. Treat a skipped item as a cap hit too. A file that raises `OSError` on read is
   one more thing you did not look at, so it sets `unknown` and then `continue`s.
6. Say which direction of error you are protecting against in a comment next to the
   flag. Here a false `0` manufactures a usage credit for code that was already in
   the repo, and a false `1` suppresses a real one.

## Gotchas

- The pre-existing implementation already had an `unknown` flag, set only on
  subprocess failure. An existing flag is not evidence that every boundary sets it.
  Grep the function for each cap constant and check that each one has a
  corresponding assignment.
- `git grep -l` returns paths in its own order. Reasoning like "the real match will
  be among the first twenty" is what the file-cap test disproves: twenty decoys
  containing the literal token sort ahead of the one file with the full pattern.
- The byte cap bites on a single file, with no file cap involved. A 240KB file with
  the match past 200KB reads clean and reports absent unless step 3 is applied to
  the text as well as the file list.
- Returning `None` costs nothing at the call site. `ledger.log_event` stores
  `preexisting_fingerprint` as a nullable INTEGER, so unknown is a first-class value
  in the schema, not a degraded one.

## Verification

- `python3 tests/test_retrieve.py` prints 26 `PASS` lines and exits 0.
- When the procedure is NOT followed it exits 1. Dropping step 3 fails
  `test_snapshot_unknown_when_match_past_file_cap` and
  `test_snapshot_unknown_when_match_past_byte_cap`, both with a bare
  `AssertionError` because the scan returned `0`. Dropping step 4 fails
  `test_snapshot_probe_cap_records_unknown`.
- Limit worth knowing: this suite only covers `fingerprint_preexisting`. A new
  capped scan added elsewhere in `scripts/` would skip the procedure and still leave
  the suite green, so the command discriminates for this function alone.
