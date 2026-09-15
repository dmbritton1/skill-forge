# E14: does a skill's trigger, or its kind, decide whether it gets used?

**Status:** design agreed in brainstorming on 2026-09-14, written before any
E14 session ran. Every criterion below is fixed before the data it governs.

## Why

In E13's trap C probe (`sf-author-verdict-from`), every probed draft gave the
same correct fix and was injected in full. Yet the two anti-skill drafts
resolved 6 of 6 runs and the three skill drafts resolved 1 of 9. In the runs
that failed, the session wrote the naive byte-exact check (`ev not in text`),
exactly as the controls did, and failed only the hidden rewrapped-quote test.

The transcript read (2026-09-14) suggests two explanations, and the probe
cannot separate them:

- **Trigger.** Skill drafts 1 and 2 said to use them when a gate *fails* or a
  named test *fails*. That never happens while writing the function, and every
  visible test passed. Skill draft 3 also mentioned *editing*
  `validate.verdict_from` and was the one skill draft that resolved (1 of 3).
- **Kind.** The anti-skills framed the naive check as a trap that "looks like
  the strictest, safest" choice, which is the code a session is about to write.

Sessions store thinking blocks empty, so neither explanation can be read off
the transcripts. Scope is not a confound: `run.py` installs every draft with
`--scope project`.

## 1. Stages

- **Stage 1 (this spec):** four hand-written drafts in a 2×2 of trigger
  (failure vs write) × kind (skill vs anti-skill), probed on trap C's author
  task. Zero distill sessions.
- **Stage 2:** runs only if a Stage 1 main effect reaches +4 (section 5). It
  re-distils trap C with the distiller prompt changed to produce the winning
  factor, and compares against the archived E13 trap C drafts. It gets its own
  spec and pre-registration, written after Stage 1's result. This spec fixes
  only when it runs and what it varies.

## 2. The four drafts

Files: `bench/drafts/E14/{sf,sw,af,aw}/SKILL.md`, for skill-failure,
skill-write, anti-failure and anti-write.

**Bases:**

- the skill cells rewrite E13 draft `C/learn-nogate/1` (0 of 3 in the probe);
- the anti-skill cells rewrite E13 draft `C/learn-failure-nogate/1` (3 of 3).

**Held identical across all four:**

- the name stem, `e14-quote-gate-rewrap`, suffixed `-sf`, `-sw`, `-af` or `-aw`;
- the fix code block:

  ```python
  ev = " ".join((f.get("evidence") or "").split())
  if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
      return "fail"
  ```

- the description of the naive check (`ev.strip()` then `ev not in text`);
- the warning against word-set, sorted-token or fuzzy matching;
- the `Do NOT use when:` clause;
- the `fingerprints:` list;
- total length, within 10% of the longest draft.

**Trigger factor.** Only the `Use when:` line in `description` differs:

- **failure (`sf`, `af`):** "Use when: a verbatim-quote evidence gate fails a
  quote that differs from the source text only by line breaks or indentation."
- **write (`sw`, `aw`):** "Use when: writing or editing a gate that checks
  model-quoted evidence against source text with a substring test, e.g.
  `evidence in text`."

**Kind factor.** Each kind's whole required format:

- **skill (`sf`, `sw`):** `kind: skill`, `verification.command: "python3
  tests/test_validate.py"`, and `## Procedure`, `## Gotchas`, `## Verification`.
- **anti-skill (`af`, `aw`):** `kind: antiskill`, one `symptoms:` list shared by
  both, and `## Trap`, `## Symptom`, `## Cause`, `## Fix`. The Trap section
  describes the naive check as looking like the strictest, safest choice.
- The body carries the same facts, arranged in each kind's sections.

**Leak guard.** No draft names a hidden test. E13's drafts named
`test_a_rewrapped_quote_still_counts_as_evidence` in a trigger or symptom, and
the author session can never see that test. No draft mentions a file under
`tests/` other than `tests/test_validate.py`.

**Validation.** Every draft must save cleanly through the real
`scripts/save_skill.py`, including the kind rules, the symptom-strength rule
and the size guard.

## 3. Delivery check (zero sessions)

`bench/e14_deliver.py` reuses `e13_qualify`'s install helpers and
`real_path_check.delivered`. For each draft, it:

- installs that draft alone into a sandboxed HOME and project;
- runs the current plugin's prompt hook on the task's author prompt;
- records whether the draft was delivered.

It writes `bench/drafts/E14/delivery.json` with each draft's path, name,
sha256 and `delivered`, and confirms the operator's library is unchanged.

**Gate:** all four must be delivered. A draft that is not delivered is edited,
never dropped. An edit may only add retrieval words to the `Use when:` line,
and the same words go into both drafts of that trigger. Edits happen before any
session.

## 4. The batch

**Composition (27 sessions):** control ×3 (no skill), and each draft ×6,
installed alone with `run.py --task sf-author-verdict-from --arm treatment
--skill-from <draft>`. Every session is sandboxed and audited, on
`claude-opus-5`.

**Order:** fixed interleaved rounds, so drift over the batch does not land on
one cell.

| round | runs |
| --- | --- |
| 1 | control, sf, sw, af, aw |
| 2 | sw, af, aw, sf |
| 3 | control, af, aw, sf, sw |
| 4 | aw, sf, sw, af |
| 5 | control, sf, sw, af, aw |
| 6 | sw, af, aw, sf |

Repeated runs (below) are appended after round 6 in the order they arise.

**Guards before the first session** (`bench/e14_probe.sh`):

- the global library is empty;
- the plugin checkout is clean;
- `run.py --check` passes;
- `run.py --sandbox-check` passes;
- `delivery.json` exists, all four drafts are delivered, and every draft's
  sha256 matches it;
- a one-word allowance probe succeeds.

**Counting rules** (`bench/e14_read.py`, rows selected by `--window`):

- **Void:** a row that `audit.counts()` rejects never counts, and its run is
  repeated.
- **Undelivered:** a draft row whose injections do not name that draft is not
  a treatment. It does not count and is repeated. A second undelivered row
  voids that cell.
- **Failed session:** a session that failed for any reason other than the
  session limit does not count and is repeated.
- **Cap:** a cell counts its first 6 valid runs in row order; the control
  counts its first 3.
- **Session limit:** a row refused at the session limit postpones the whole
  batch. The script stops, and the batch is re-run whole later as one fresh
  batch. Never stitched.
- **Control:** if the control resolves even once, the batch is void.

A batch is complete when the control has 3 valid runs and every cell has 6
valid runs or is void. Both effects use all four cells, so if any cell is void
neither effect is computed: the report gives the cell table and says which
cell voided.

## 5. Criterion

Let SF, SW, AF, AW be each cell's resolved count out of 6.

- **Trigger effect** = (SW + AW) − (SF + AF)
- **Kind effect** = (AF + AW) − (SF + SW)

Bands, applied to each effect separately:

| effect | reading |
| --- | --- |
| +4 or more | the factor matters (write beats failure; anti-skill beats skill) |
| +2 or +3 | ambiguous; no claim |
| −1 to +1 | no large effect |
| −2 or −3 | ambiguous in the other direction; no claim |
| −4 or less | a clear effect in the opposite direction; reported, not pre-registered |

Reported alongside, never a threshold:

- Fisher's exact p (two-sided) for each effect, on its pooled 2×2 of 12 vs 12;
- the full four-cell table. An interaction is described, never claimed.

**Baseline check.** E13 predicts SF ≤ 1 and AF ≥ 5. If either misses, the
report flags that the rewrite moved the baseline, and both effects are read
with that caveat.

**Readings:**

- **trigger effect only:** the lever is the distiller's `Use when:` wording;
- **kind effect only:** the Trap framing is what gets acted on;
- **both:** Stage 2 targets the larger effect (trigger on a tie);
- **neither:** the E13 split does not replicate with controlled drafts, and was
  likely specific to those drafts.

## 6. Outputs

- A register row and a results section in `bench/RESULTS.md`, whatever the
  outcome, including a postponed or void batch.
- `bench/drafts/E14/` with the four drafts and `delivery.json`, committed
  before the batch.
- The batch's `results.jsonl` rows, committed.

## 7. Constraints

- Nothing under `scripts/` changes.
- `scripts/retrieve.py`, `scripts/detect.py`, `scripts/reconcile.py` and
  `bench/real_path_check.py` are not touched.
- No E13 file changes; E13's readers and results stay as they are.
- No absolute home path in committed files.
- Guard committing steps with an explicit `|| exit 1`.
