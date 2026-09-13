#!/usr/bin/env bash
# E12 -- does an irrelevant injected skill actively hurt? Composition is
# pre-registered:
# docs/superpowers/specs/2026-09-13-e12-irrelevant-injection-harm-design.md
#
# Three arms per task IN ONE BATCH, n=6 per cell, 36 sessions.
#
#   R  the skill distilled from THIS task's own bug   (561-574 tokens)
#   I  arrow-tzinfo-string-trap, no bearing on it     (544 tokens)
#   C  nothing
#
# Arm R's mapping is the SWAP of tasks.json's crossover pairing: this
# experiment wants genuine relevance, not same-class transfer.
#   escaping   (22ddf37) -> serialization-corrupts-matching, distilled from 22ddf37
#   truncation (ab4acfe) -> lossy-transform-false-negative,  distilled from ab4acfe
#
# Payloads are size-matched within 30 tokens on purpose (spec 3.2): a two-arm
# C-vs-I test confounds irrelevance with the cost of injected context, and
# three size-matched arms separate them.
#
# C runs LAST in each task so control is measured under the same conditions as
# its own treatments rather than at the batch's edge. Same-batch control is
# E5's rule and is what caught E10's break.
#
# Reading order is fixed by the spec and is not optional: section 4.2's
# validity conditions FIRST (control >= 10/12 pooled, and every treatment row
# naming its skill in `injections`), and only then section 4.1's criterion.
#
# The delivery smoke test of 2026-09-13T15:33:34 is EXCLUDED from every
# analysis here (spec 4.3). It confirmed --skill-from lands the skill in
# `injections` on a repair-mode task, which no batch had ever exercised.
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R"

# A control cell must receive NOTHING. retrieve.py ranks the global store, so
# one global skill scoring against these prompts would turn a floor
# measurement into a quiet treatment run while the row still read "control".
python3 -c "
import sys; sys.path.insert(0,'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty -- control would not be control"; exit 1; }

# --skill-from must be ABSOLUTE: install_skill shells save_skill.py with cwd
# set to the throwaway clone, so a relative path resolves against the clone.
S="$R/bench/skills"
IRRELEVANT="$S/arrow-tzinfo-string-trap.md"

# $1 task, $2 the skill distilled from THIS task's own bug
arms() {
  local task="$1" relevant="$2"
  echo "### R  $task  (relevant: $(basename "$relevant"))"
  python3 bench/run.py --task "$task" --runs 6 --arm treatment --skill-from "$relevant"

  echo "### I  $task  (irrelevant: arrow-tzinfo-string-trap)"
  python3 bench/run.py --task "$task" --runs 6 --arm treatment --skill-from "$IRRELEVANT"

  echo "### C  $task  (nothing)"
  python3 bench/run.py --task "$task" --runs 6 --arm control
}

arms sf-escaping-breaks-symptom-match "$S/serialization-corrupts-matching.md"
arms sf-truncation-reports-absent     "$S/lossy-transform-false-negative.md"
echo "### E12 DONE"
