#!/usr/bin/env bash
# E10 -- does a wrong-bug skill hurt at prompt time? Composition is
# pre-registered:
# docs/superpowers/specs/2026-09-11-e10-prompt-time-budget-design.md
#
# Four arms per task IN ONE BATCH, in the order M, P, S, C (spec section 4),
# response_text first. M = the matched skill alone at the shipped 1200.
# P = the pair at 2000. S = the consolidated seven at 2000. C = nothing.
# n=3 per cell, 24 sessions.
#
# Check the session meter BEFORE running this; `claude -p` exits 1 when the
# session allowance is gone, and a truncated batch is postponed, not answered.
#
# Arms M and C carry no budget segment, so 12 of the 24 clone names reuse
# Q1/E9 names -- accepted: prepare() rmtrees those /tmp copies, extracted
# evidence is unaffected. Analyses must join on (clone, batch), not clone alone.
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R"

# The bench passes --plugin-dir "$R", so the hook that fires inside every
# session is THIS tree's scripts/retrieve.py. Run from a tree without the
# budget lever and P and S silently run at 1200 while every row still
# records 2000 -- 24 sessions of data that looks valid and is not.
python3 -c "
import os,sys; sys.path.insert(0,'scripts'); import inspect, retrieve
src = inspect.getsource(retrieve.run_hook)
sys.exit(0 if 'SKILLFORGE_INJECT_BUDGET' in src else 1)
" || { echo "FATAL: retrieve.run_hook does not read SKILLFORGE_INJECT_BUDGET"; exit 1; }

# --skill-from must be ABSOLUTE: install_skill shells save_skill.py with cwd
# set to the clone, so a relative path resolves against the clone.
D="$R/bench/distilled"
A_SKILL="$D/A/learn-failure/1/SKILL.md"    # 759, trap A, wants response_text
B_SKILL="$D/B/consolidated/1/SKILL.md"     # 1088, trap B, wants fingerprint
SEVEN=("$A_SKILL" \
       "$D/A/learn-failure/2/SKILL.md" \
       "$D/A/learn-failure/3/SKILL.md" \
       "$D/A/consolidated/1/SKILL.md" \
       "$B_SKILL" \
       "$D/B/learn-nogate/1/SKILL.md" \
       "$D/B/learn-nogate/2/SKILL.md")

# $1 task, $2 its matched skill, $3 the other half of the pair
arms() {
  local task="$1" matched="$2" other="$3" s
  local plus=()

  echo "### M  $task  (matched alone, shipped budget)"
  python3 bench/run.py --task "$task" --runs 3 --arm treatment \
    --skill-from "$matched"

  echo "### P  $task  (pair, budget 2000)"
  python3 bench/run.py --task "$task" --runs 3 --arm treatment \
    --skill-from "$matched" --plus-skill "$other" --inject-budget 2000

  for s in "${SEVEN[@]}"; do
    [ "$s" = "$matched" ] || plus+=(--plus-skill "$s")
  done
  echo "### S  $task  (seven, budget 2000, ${#plus[@]} extras passed / 2)"
  python3 bench/run.py --task "$task" --runs 3 --arm treatment \
    --skill-from "$matched" "${plus[@]}" --inject-budget 2000

  echo "### C  $task"
  python3 bench/run.py --task "$task" --runs 3 --arm control
}

arms sf-author-response-text "$A_SKILL" "$B_SKILL"
arms sf-author-fingerprint-preexisting "$B_SKILL" "$A_SKILL"
echo "### E10 DONE"
