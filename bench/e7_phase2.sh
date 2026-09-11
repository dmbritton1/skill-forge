#!/usr/bin/env bash
# E7 phase 2 -- the batch composition is pre-registered, so it lives in git
# rather than in /tmp. Spec: docs/superpowers/specs/2026-09-10-e7-novelty-gate-design.md
#
# Section 5 requires arm C interleaved rather than run as a trailing block, and
# section 5.1 requires the WHOLE of this to run in one batch -- not the
# remainder after the 2026-09-10 interruption. Check the session meter first.
# 24 sessions, roughly an hour.
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R"

run_drafts() {          # $1 trap letter, $2 probe task
  for d in 1 2 3; do
    echo "### $1/learn-nogate/$d -> $2"
    # --skill-from must be ABSOLUTE: install_skill shells save_skill.py with
    # cwd set to the clone, so a relative path resolves against the clone.
    python3 bench/run.py --task "$2" --runs 3 --arm treatment \
      --skill-from "$R/bench/distilled/$1/learn-nogate/$d/SKILL.md"
  done
}

echo "### control sf-author-response-text"
python3 bench/run.py --task sf-author-response-text --runs 3 --arm control
run_drafts A sf-author-response-text

echo "### control sf-author-fingerprint-preexisting"
python3 bench/run.py --task sf-author-fingerprint-preexisting --runs 3 --arm control
run_drafts B sf-author-fingerprint-preexisting

echo "### PHASE 2 DONE"
