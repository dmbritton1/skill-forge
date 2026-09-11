#!/usr/bin/env bash
# E9 phase 2 -- does a consolidated skill still work?
# Spec: docs/superpowers/specs/2026-09-11-e9-consolidation-design.md
#
# Three arms per task IN ONE BATCH, order R, K, C (spec section 4).
# R = the named representative member. K = the consolidated merge. C = none.
# n=3 per cell, 18 sessions. Check the session meter first.
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R"

arm() {                  # $1 label, $2 task, $3 absolute SKILL.md
  echo "### $1  $2  <- $(echo "$3" | sed "s|$R/bench/distilled/||")"
  # --skill-from must be ABSOLUTE: install_skill shells save_skill.py with cwd
  # set to the clone, so a relative path resolves against the clone.
  python3 bench/run.py --task "$2" --runs 3 --arm treatment --skill-from "$3"
}

arm R sf-author-response-text "$R/bench/distilled/A/learn-nogate/2/SKILL.md"
arm K sf-author-response-text "$R/bench/distilled/A/consolidated/1/SKILL.md"
echo "### C  sf-author-response-text"
python3 bench/run.py --task sf-author-response-text --runs 3 --arm control

arm R sf-author-fingerprint-preexisting "$R/bench/distilled/B/learn/1/SKILL.md"
arm K sf-author-fingerprint-preexisting "$R/bench/distilled/B/consolidated/1/SKILL.md"
echo "### C  sf-author-fingerprint-preexisting"
python3 bench/run.py --task sf-author-fingerprint-preexisting --runs 3 --arm control

echo "### E9 DONE"
