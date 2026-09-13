#!/usr/bin/env bash
# E11 -- trap screening. Composition is pre-registered:
# docs/superpowers/specs/2026-09-13-e11-trap-screening-design.md
#
# Control only, no skill installed in any cell. A control floor is a property
# of the task's stub and tests, so there is nothing a treatment arm could add.
#
#   A  sf-escaping-breaks-symptom-match   n=6   candidate
#   B  sf-truncation-reports-absent       n=6   candidate
#   R  sf-author-fingerprint-preexisting  n=3   same-batch reference (0/18)
#
# 15 sessions. Criterion (spec section 4.1): 0/6 admits, any non-zero rejects.
# If R resolves >= 1/3 the whole screen is void (section 4.2) -- a floor
# measured while the environment moves is not a floor.
#
# Check the session meter BEFORE running this; `claude -p` exits 1 when the
# session allowance is gone, and a truncated batch is postponed, not answered.
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R"

# A control cell must receive NOTHING. retrieve.py ranks the global store, so
# a single global skill that scores against these prompts turns a floor
# measurement into a quiet treatment run -- and the row would still say
# "control". Project-scoped entries and trust.json keys are the operator's own
# working state and are NOT injection sources, so they are deliberately not
# guarded here: libguard's docstring is explicit that asserting on those fires
# on a clean batch.
python3 -c "
import sys; sys.path.insert(0,'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty -- control would not be control"; exit 1; }

# Both candidates are mode=repair, so run.py::one scores the tree BEFORE each
# session and prints 'already passing at baseline' if a graded test starts
# green. Watch the log for it: such a cell measures nothing.
cell() {
  local task="$1" n="$2" label="$3"
  echo "### $label  $task  (control, n=$n)"
  python3 bench/run.py --task "$task" --runs "$n" --arm control
}

cell sf-escaping-breaks-symptom-match  6 "A"
cell sf-truncation-reports-absent      6 "B"
cell sf-author-fingerprint-preexisting 3 "R"
echo "### E11 DONE"
