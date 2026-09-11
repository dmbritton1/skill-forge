---
name: capped-scan-reports-unknown
kind: skill
scope: global
description: >
  A bounded presence check must return tri-state (found / absent / unknown) and
  report unknown wherever a cap truncated the search, because a partial sweep
  that found nothing cannot tell absent from unexamined.
  Use when: writing or fixing a "does X already exist here?" probe that has any
  budget on it (file-count cap, byte cap, timeout, candidate cap, result-page
  cap), especially inside a blocking hook or request path; when a caller stores
  or acts on that answer (usage credit, dedupe, skip-if-present).
  Do NOT use when: the search is exhaustive with no cap; when the caller only
  needs a best-effort hint and treats absent and unknown identically; when the
  probe is an unbounded batch job that can afford to scan everything.
verification.command: "python3 tests/test_retrieve.py"
fingerprints:
  - "return None if unknown else 0"
  - "if len(probes) > MAX_PROBES: return None"
  - "if len(text) > MAX_BYTES: unknown = True"
provenance:
  repo: /private/tmp/skillforge-bench/sf-truncation-reports-absent-distill-learn-nogate-1
  commit: 589f9da
  distilled: 2026-09-10
---

## Procedure

1. Make the return type tri-state before writing any scan logic: a truthy
   found value, a falsy absent value, and `None` for unknown. A boolean
   return has nowhere to put "I could not tell", so it will lie.
2. Enumerate every cap in the function. There is usually more than one, and
   they are easy to miss because each looks innocent on its own. Typical set:
   candidates truncated (`names[:MAX_FILES]`), content truncated
   (`text[:MAX_BYTES]`), work-unit budget (how many probes/queries), and a
   subprocess or network timeout.
3. Declare one `unknown = False` flag and set it `True` at every one of those
   points, right where the truncation happens, not at the call site. Compare
   the pre-truncation length against the cap: `if len(names) > MAX_FILES` and
   `if len(text) > MAX_BYTES`. Slicing is silent, so the comparison is the
   only place the loss is visible.
4. For a budget that is known to be blown before any work starts (more
   patterns to check than the probe budget allows), return `None` up front
   instead of checking the first N. A partial sweep that happens to find a
   match is fine, but one that finds nothing is indistinguishable from
   absent, and the up-front bail also costs zero subprocesses.
5. Keep the positive short-circuit: return found the moment a match is
   confirmed, even if `unknown` is already set. A confirmed hit is certain
   regardless of what was skipped; only the negative answer is in doubt.
6. End with `return None if unknown else 0`. Absent is only reported when
   the search actually completed.
7. Make the caller store the three states distinctly (a nullable column, not
   a boolean default). If the storage layer collapses `None` into the absent
   value, the tri-state in the function buys nothing.

## Gotchas

- The bug is invisible in the happy path. Small-repo tests pass either way,
  so the caps need tests that deliberately put the real match past each one:
  N+1 candidates with the true hit sorted last, and padding longer than the
  byte cap with the true hit after it.
- Truncation caps interact with the ordering of the underlying tool. A
  candidate list truncated with `[:N]` inherits whatever order the tool
  emitted (`git grep -l` is alphabetical), so the match you would have found
  may be exactly the one dropped. Do not assume the first N are the likely N.
- A timeout or a non-zero exit from the helper process is also unknown, not
  absent. Exit codes need splitting by meaning: for `git grep`, 1 is a real
  "no match" and anything else is "not a usable repo".
- Setting `unknown` and then `continue`-ing past a bad candidate is correct;
  setting it and then `return 0` anywhere is the bug this skill prevents.

## Verification

- `python3 tests/test_retrieve.py` should print PASS for every test, including
  the cases that place the match past the file cap, past the byte cap, and
  behind an over-budget probe count.
- What it does when the procedure was NOT followed: those three tests fail
  with a bare `AssertionError`, because the capped scan returns the absent
  value `0` where the tests demand `None`. A missing probe budget fails
  louder, with `AttributeError` on the absent cap constant. The suite does
  not pass by default: an implementation that slices without flagging the
  truncation cannot make it green.
- In a repo without this suite, the equivalent check is a test that seeds the
  match beyond each cap and asserts the unknown value, then running it. A
  check that only exercises an under-cap input passes with or without the
  procedure and proves nothing.
