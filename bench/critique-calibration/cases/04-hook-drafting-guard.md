---
name: hook-drafting-guard
kind: skill
description: Add the SKILLFORGE_DRAFTING guard to a hook script's main() so it goes inert inside a drafter subprocess. Use when adding a new hook to hooks/hooks.json. Do NOT use for non-hook scripts such as save_skill.py or validate.py, which are spawned deliberately and must still run.
verification.command: python3 tests/test_guard.py
fingerprints:
  - "SKILLFORGE_DRAFTING"
  - "hooks.json"
provenance:
  repo: dmbritton1/skill-forge
  distilled: 2026-08-29
---

## Procedure

1. Open the hook's script in `scripts/` and find its `main()`.

2. Make this the **first statement** of `main()`, before any argument
   parsing and before anything reads stdin:

       if os.environ.get("SKILLFORGE_DRAFTING"):
           return 0

3. It must come before the stdin read specifically. A drafter subprocess
   sends no hook payload, so a hook that reads stdin first blocks or
   consumes input that was never meant for it. Returning early avoids both.

4. Add one test to `tests/test_guard.py` named `test_<script>_is_inert`,
   copying the body of the existing `test_detect_is_inert` and substituting
   your module. The suite names each hook explicitly; it will not discover a
   new one on its own.

## Preconditions

- Python 3.9 or later on PATH as `python3`. No third-party packages are
  installed or needed, and pytest is not available.
- Run from the repository root, so `tests/` and `scripts/` both resolve.
- The script already has a `main()` and is registered in `hooks/hooks.json`.

## Verification

`python3 tests/test_guard.py` exits 0.

The suite sets `SKILLFORGE_DRAFTING=1`, replaces `sys.stdin` with a reader
that counts its own reads, calls each hook's `main()`, and asserts three
things: it returns 0, it writes nothing to stdout, and it never reads stdin.
Omitting the guard leaves the hook reading stdin, so the read count is no
longer zero and the test fails.
