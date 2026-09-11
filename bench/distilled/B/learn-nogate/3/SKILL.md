---
name: truncation-reports-unknown
kind: skill
scope: project
description: >
  Make every early-exit cap in a bounded scan report unknown instead of a
  negative result, so "we did not look" is never recorded as "it is not there".
  Use when: writing or fixing a function that returns found / not-found /
  unknown over a capped search (file-count caps, byte caps, probe or time
  budgets, skipped unreadable files), or when a test asserts unknown and the
  code returns the absent value.
  Do NOT use when: the function is two-valued and has no way to express
  unknown, or the scan is exhaustive with no cap at all.
verification.command: "python3 tests/test_retrieve.py"
fingerprints:
  - "if len(names) > SNAPSHOT_MAX_FILES:"
  - "fh.read(SNAPSHOT_MAX_BYTES + 1)"
  - "len(fingerprints) > SNAPSHOT_MAX_PROBES"
provenance:
  repo: /private/tmp/skillforge-bench/sf-truncation-reports-absent-distill-learn-nogate-3
  commit: 589f9da
  distilled: 2026-09-10
---

## Procedure

1. Find the function that answers three ways: present, absent, unknown. In
   this repo that is `fingerprint_preexisting` in `scripts/retrieve.py`, which
   returns `1 / 0 / None`. The absent value is the dangerous one, because it
   is a claim about everything the scan did not read.

2. Enumerate every place the scan stops early. Do not fix only the cap the
   failing test names; they are siblings of one bug and the test suite
   usually names one of them. The recurring set:
   - the candidate list from the search tool, sliced to a max-results cap
   - each candidate's content, read up to a byte or character cap
   - the number of patterns or probes, capped by a latency budget
   - every `except OSError: continue` that skips a candidate entirely

3. At each of those, set the unknown flag rather than falling through to the
   negative return.

4. Where the budget is blown before any work starts, return unknown up front
   instead of probing a prefix. A positive found in a prefix is still sound,
   but the caller cannot tell a prefix answer from a full one, and a
   short-circuit is the only version a test can prove fired.

5. Detect truncation by fetching one unit past the cap, never by comparing
   the result length to the cap: `fh.read(CAP + 1)` then `len(text) > CAP`,
   and `len(hits) > MAX` on the unsliced list. A file exactly CAP bytes long
   is otherwise indistinguishable from a truncated one.

6. Let only the positive result return early. The negative return stays
   gated at the end: `return None if unknown else 0`.

## Gotchas

- Reading the whole file and then slicing (`path.read_text()[:CAP]`) loses
  the truncation signal and pulls the entire file into memory. Bound the read
  itself.
- `git grep -l` returns paths in sorted order, so a file-count cap hides
  exactly the late-alphabet file the match lives in. That is the case worth a
  test, not the happy path.
- Check the consumer before changing the return: unknown has to survive
  storage. Here it lands in a nullable `preexisting_fingerprint` column, so
  `None` stays `None` and is never coerced to 0.
- A skipped unreadable candidate is a truncation too, even though nothing was
  capped.

## Verification

- `python3 tests/test_retrieve.py` passes all 26 tests.
- It discriminates: three tests build a repo where the match sits past a cap
  (past the file cap, past the byte cap, past the probe budget) and assert the
  result is unknown. Code that reports absent on truncation fails all three
  with `AssertionError`, and omitting the probe budget fails with
  `AttributeError: module 'retrieve' has no attribute 'SNAPSHOT_MAX_PROBES'`.
- In another repo the equivalent check is a test that places the match beyond
  each cap in turn and asserts unknown; a test that only exercises a match
  inside the caps passes either way and proves nothing.
