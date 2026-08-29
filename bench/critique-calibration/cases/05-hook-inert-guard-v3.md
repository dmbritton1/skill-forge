---
name: hook-inert-guard
kind: skill
scope: project
description: >
  Make a SkillForge hook go inert inside a drafter subprocess by guarding
  main() on SKILLFORGE_DRAFTING before it reads stdin.
  Use when: adding a hook to hooks/hooks.json, or editing the top of an
  existing hook's main() in scripts/detect.py, retrieve.py, reconcile.py or
  sync.py.
  Do NOT use when: writing a worker that is spawned deliberately rather than
  fired by the harness — save_skill.py, draft.py and validate.py must still
  run inside a drafting session, and validate.py's own guard is an inherited
  context check, not this pattern.
verification.command: "python3 tests/test_guard.py"
fingerprints:
  - "os.environ.get(\"SKILLFORGE_DRAFTING\")"
  - "SKILLFORGE_DRAFTING=1 in the child"
provenance:
  repo: dmbritton1/skill-forge
  commit: 4e57f87
  distilled: 2026-08-29
---

## Procedure

1. Open the hook's script in `scripts/` and find `main()`.

2. Confirm the file imports `os` at the top. Every current hook already
   does; add `import os` if yours does not, or step 3 raises `NameError`.

3. Make this the first statement of `main()`, above argument parsing and
   above anything that touches stdin:

       if os.environ.get("SKILLFORGE_DRAFTING"):
           return 0

4. Keep it above the stdin read specifically. A drafter subprocess sends no
   hook payload, so a hook that reads stdin first blocks on input that is
   never coming. Returning before the read avoids that, and returning 0
   keeps the harness's control channel clean.

5. Add a test to `tests/test_guard.py` named `test_<script>_is_inert`,
   copying the body of `test_detect_is_inert` and substituting your module.
   Do this even for an existing hook that has no test yet: the suite checks
   only the hooks it names.

   There is no registration step. The file's `__main__` runner collects
   every `test_*` function out of `globals()`, so defining the function is
   all that is required.

## Gotchas

- The guard belongs only on scripts the harness fires. A worker that another
  script spawns on purpose must not carry it: if the spawner also sets
  `SKILLFORGE_DRAFTING=1` in the child, the worker returns 0 as its first
  statement and does nothing, and no unit test can see it because the suites
  are forbidden from spawning real subprocesses.

- A spawner should therefore pass `env=os.environ` unchanged rather than
  `dict(os.environ, SKILLFORGE_DRAFTING="1")`. Passing it through preserves
  a real inherited-context check — the flag is set when the parent genuinely
  is a drafter — instead of manufacturing one.

## Verification

- `python3 tests/test_guard.py` exits 0.

  The suite sets `SKILLFORGE_DRAFTING=1`, replaces `sys.stdin` with a reader
  that counts its own reads, calls each hook's `main()`, and asserts three
  things: it returns 0, it writes nothing to stdout, and its stdin read count
  is zero. Omitting the guard from step 3 leaves the hook reading stdin, so
  that count is no longer zero and this command fails.
