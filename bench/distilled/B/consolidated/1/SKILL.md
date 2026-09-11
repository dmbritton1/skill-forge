---
name: capped-scan-reports-unknown-not-absent
kind: skill
scope: project
description: >
  Every early-exit cap in a bounded scan (file-count cap, byte cap, probe budget,
  skipped unreadable candidate) must widen the result to unknown, never fall
  through to the negative/absent value -- and the cap must be detected before the
  slice that destroys the evidence. Use when: writing or fixing a
  found/absent/unknown function over a capped search -- fingerprint_preexisting
  in retrieve.py, symptom or verification matching in detect.py, or any new probe
  with a candidate/byte/probe cap. Do NOT use when: the function is two-valued
  with no way to express unknown, the scan is unbounded (exhaustive, no cap at
  all), the caller only needs a boolean and writes no event row, or you are
  tuning the cap constants themselves rather than fixing how a cap hit gets
  reported.
verification.command: "python3 tests/test_retrieve.py"
fingerprints:
  - "if len(names) > SNAPSHOT_MAX_FILES:"
  - "fh.read(SNAPSHOT_MAX_BYTES + 1)"
  - "len(fingerprints) > SNAPSHOT_MAX_PROBES"
  - "if len(text) > SNAPSHOT_MAX_BYTES:"
  - "if len(probes) > SNAPSHOT_MAX_PROBES:"
---

## Procedure

1. List every cap the scan enforces before touching code. In
   `fingerprint_preexisting` (`scripts/retrieve.py`) there are four: subprocess
   timeout, probe count (`SNAPSHOT_MAX_PROBES`), candidate-file count
   (`SNAPSHOT_MAX_FILES`), and bytes read per file (`SNAPSHOT_MAX_BYTES`). A cap
   you didn't enumerate is a cap whose truncation you will report as `0`. Same
   shape applies to any new capped probe, or to matching in `detect.py`.

2. Carry one `unknown = False` flag through the scan and set it at every
   boundary, including a skipped candidate (`except OSError: continue` still
   means "did not look"). Only a positive match may return early -- presence is
   the one conclusion a partial sweep can support. End with
   `return None if unknown else 0`.

3. Detect each cap hit **before** the operation that discards the evidence:
   fetch one unit past the cap and compare, never compare the result to the cap
   after slicing. `fh.read(CAP + 1)` then `len(text) > CAP`; `len(hits) > MAX` on
   the unsliced list. `path.read_text()[:CAP]` has already lost the signal --
   bound the read itself.

4. Where the budget is blown before work starts, short-circuit: return unknown
   immediately rather than probing a prefix. A positive found in a prefix is
   still sound, but the caller can't tell a prefix answer from a full one, and
   probing the first few makes the result depend on an ordering nobody controls.

5. Check the consumer before finalizing the return: unknown has to survive
   storage. `ledger.log_event` stores `preexisting_fingerprint` as a nullable
   INTEGER, so `None` stays `None` and is never coerced to 0.

6. Note which direction of error you're protecting against, in a comment by the
   flag: a false `0` manufactures a usage credit for pre-existing code, a false
   `1` suppresses a real one.

## Gotchas

- `git grep -l` returns paths in sorted order, so a cap hides exactly the
  late-sorting file the match lives in -- that's the case worth a test; twenty
  decoys sorting ahead of the real match disprove "it'll be in the first few".
- An existing `unknown` flag (e.g. set only on subprocess failure) is not
  evidence every boundary sets it -- grep the function for each cap constant and
  confirm each has a matching assignment.
- The byte cap bites inside a single file with no file-cap involved: a 240KB
  file with the match past 200KB reads clean and reports absent unless the text
  length is checked the same way as the file list.

## Verification

- `python3 tests/test_retrieve.py` passes all 26 tests (prints 26 `PASS` lines,
  exits 0).
- Discriminates: tests place the match past each cap in turn (file cap, byte
  cap, probe budget) and assert unknown. Code that reports absent on truncation
  fails with `AssertionError`; omitting the probe budget fails with
  `AttributeError: module 'retrieve' has no attribute 'SNAPSHOT_MAX_PROBES'`. A
  test that only exercises a match inside the caps passes either way and proves
  nothing.
- Coverage limit: this suite only covers `fingerprint_preexisting`. A new capped
  scan added elsewhere in `scripts/` would skip the procedure and still leave
  the suite green.
