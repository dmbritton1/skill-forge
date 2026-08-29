---
name: verify-skillforge-suites
kind: skill
description: Run SkillForge's test suites after changing scripts/. Use when verifying a Python change in this repo. Do NOT use for changes outside scripts/ or tests/.
verification.command: python3 tests/test_ledger.py
fingerprints:
  - "tests/test_"
  - "python3 tests"
provenance:
  repo: dmbritton1/skill-forge
  distilled: 2026-08-28
---

## Procedure

1. From the repository root, run each suite directly. There is no test
   runner and pytest is not installed:

       python3 tests/test_ledger.py

2. Repeat for every file matching `tests/test_*.py`. Each is standalone and
   exits 0 when it passes, 1 when any test fails.

3. A suite prints one `PASS <name>` line per test. A failure prints
   `FAIL <name>: <repr>` and the run still continues to the end.

## Preconditions

- Python 3.9 or later on PATH as `python3`. No third-party packages are
  needed or installed.
- Run from the repository root, so that `tests/` and `scripts/` are both
  relative to the working directory.

## Verification

`python3 tests/test_ledger.py` exits 0 and prints no `FAIL` lines.
