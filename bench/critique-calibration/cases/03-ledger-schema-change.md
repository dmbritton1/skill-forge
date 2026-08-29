---
name: ledger-schema-change
kind: skill
description: Change a table or view in scripts/ledger.py without breaking existing databases. Use when editing the SCHEMA string. Do NOT use for query-only changes that leave SCHEMA untouched.
verification.command: python3 tests/test_ledger.py
fingerprints:
  - "CREATE VIEW"
  - "SCHEMA_VERSION"
provenance:
  repo: dmbritton1/skill-forge
  distilled: 2026-08-29
---

## Procedure

1. Edit the `SCHEMA` string in `scripts/ledger.py`.

2. If you changed a VIEW, stop and add a migration. `CREATE VIEW IF NOT
   EXISTS` does not replace a view that already exists, so every database
   created before your edit keeps the old definition forever.

3. Increment `SCHEMA_VERSION` by one.

4. Add an entry to `MIGRATIONS` for that new version whose statements
   `DROP VIEW IF EXISTS <name>`. The unconditional `executescript(SCHEMA)`
   in `connect()` then recreates it with your new definition.

5. Adding a TABLE needs no migration. `CREATE TABLE IF NOT EXISTS` reaches
   every existing database through that same unconditional `executescript`.

## Preconditions

- Python 3.9 or later on PATH as `python3`; no third-party packages are
  installed or needed.
- Run from the repository root, so `tests/` and `scripts/` both resolve.

## Verification

`python3 tests/test_ledger.py` exits 0. That suite builds a database at the
old schema and asserts the renamed column is present after `connect()`, so
it fails if step 3 or step 4 was skipped.
