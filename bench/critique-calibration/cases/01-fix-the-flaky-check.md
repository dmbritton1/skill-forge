---
name: fix-the-flaky-check
kind: skill
description: Fix the flaky check when it acts up. Use when the check is being flaky. Do NOT use otherwise.
verification.command: python3 tests/test_ledger.py
fingerprints:
  - "flaky check"
  - "acting up"
provenance:
  repo: dmbritton1/skill-forge
  distilled: 2026-08-28
---

## Procedure

1. Apply the same fix we used last time — the one from the earlier session
   where the timestamps were off.
2. Update the affected file the way we discussed, being careful to keep the
   existing behaviour intact.
3. If it still misbehaves, adjust the values until the check settles down.
4. Make sure everything still works afterwards.

## Verification

Confirm the check is no longer flaky.
