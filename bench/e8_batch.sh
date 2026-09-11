#!/usr/bin/env bash
# E8 phase -- library depth. Composition is pre-registered:
# docs/superpowers/specs/2026-09-11-e8-library-depth-design.md
#
# Three arms per task IN ONE BATCH, in the order M, L, C (spec section 4).
# M = the named matched skill alone. L = all ten distilled skills. C = none.
# n=3 per cell, 18 sessions. Check the session meter first.
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R"

ALL=$(find "$R/bench/distilled" -name SKILL.md | sort)

arm_M_and_L() {          # $1 probe task, $2 matched SKILL.md (absolute)
  local task="$1" matched="$2"
  echo "### M  $task  <- $(echo "$matched" | sed "s|$R/bench/distilled/||")"
  # --skill-from must be ABSOLUTE: install_skill shells save_skill.py with cwd
  # set to the clone, so a relative path resolves against the clone.
  python3 bench/run.py --task "$task" --runs 3 --arm treatment \
    --skill-from "$matched"

  # Arm L is the matched skill PLUS the other nine, so all ten are installed.
  local plus=()
  local s
  for s in $ALL; do
    [ "$s" = "$matched" ] || plus+=(--plus-skill "$s")
  done
  echo "### L  $task  <- all 10 (${#plus[@]} extras passed / 2)"
  python3 bench/run.py --task "$task" --runs 3 --arm treatment \
    --skill-from "$matched" "${plus[@]}"
}

arm_M_and_L sf-author-response-text \
  "$R/bench/distilled/A/learn-nogate/2/SKILL.md"
echo "### C  sf-author-response-text"
python3 bench/run.py --task sf-author-response-text --runs 3 --arm control

arm_M_and_L sf-author-fingerprint-preexisting \
  "$R/bench/distilled/B/learn/1/SKILL.md"
echo "### C  sf-author-fingerprint-preexisting"
python3 bench/run.py --task sf-author-fingerprint-preexisting --runs 3 --arm control

echo "### E8 DONE"
