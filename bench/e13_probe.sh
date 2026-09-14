#!/usr/bin/env bash
# E13 probe batch for one trap. Composition is pre-registered:
# docs/superpowers/specs/2026-09-13-e13-author-traps-design.md, section 7.
#
# 3 control sessions on the trap's author task, then each deliverable draft
# (bench/distilled/<trap>/qualification.json) installed alone, 3 runs each.
# The batch is void if the control resolves once. A session refused at the
# session limit postpones the whole batch: the script stops, and the batch is
# re-run whole later. A treatment row that did not inject its draft is re-run by
# hand: python3 bench/run.py --task <task> --runs 1 --arm treatment --skill-from <abs draft>
#
# Read with: python3 bench/e13_probe_read.py --trap <trap> --window <PROBE_START> -
# Usage: bash bench/e13_probe.sh --trap C [--dry-run]
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
TRAP=""; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --trap) TRAP="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown argument: $1"; exit 1 ;;
  esac
done
[ -n "$TRAP" ] || { echo "usage: bash bench/e13_probe.sh --trap C [--dry-run]"; exit 1; }
Q="bench/distilled/$TRAP/qualification.json"
[ -f "$Q" ] || { echo "FATAL: $Q missing -- run bench/e13_qualify.py --trap $TRAP --write first"; exit 1; }

python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty"; exit 1; }
if [ -n "$(git status --porcelain -- scripts hooks skills .claude-plugin commands)" ]; then
  echo "FATAL: uncommitted changes in the plugin under test"; exit 1
fi
if ! git diff --quiet 9cbb472 -- scripts hooks; then
  echo "FATAL: scripts/ or hooks/ have drifted from 9cbb472 -- the qualification's NEW_REF no longer matches the plugin under test"
  exit 1
fi
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }
# Sandbox spec section 4.4: zero sessions, before the first one.
python3 bench/run.py --sandbox-check || { echo "FATAL: sandbox self-check failed"; exit 1; }

TASK="$(python3 -c "import json; print(json.load(open('$Q'))['task'])")"
DRAFTS=()
while IFS= read -r p; do
  [ -n "$p" ] && DRAFTS+=("$p")
done < <(python3 -c "
import json
for r in json.load(open('$Q'))['drafts']:
    if r['deliverable']:
        print(r['path'])
")
[ "${#DRAFTS[@]}" -gt 0 ] || { echo "FATAL: no deliverable draft -- trap $TRAP is not a working trap (section 7)"; exit 1; }
echo "task: $TASK"
echo "deliverable drafts: ${DRAFTS[*]}"

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed; a real run probes the allowance, then 3 control and 3 runs per draft"
  exit 0
fi

PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

START="$(date +%Y-%m-%dT%H:%M:%S)"
echo "PROBE_START $START"
check_postponed() {
  local out
  out="$(python3 bench/e13_probe_read.py --trap "$TRAP" --window "$START" - 2>&1)"
  echo "$out"
  case "$out" in
    "batch: postponed"*) echo "STOP: session limit -- re-run this whole batch later as one fresh batch"; exit 1 ;;
  esac
}

echo "### control $TASK (n=3)"
python3 bench/run.py --task "$TASK" --runs 3 --arm control || echo "run.py exited non-zero for the control"
check_postponed
for d in "${DRAFTS[@]}"; do
  echo "### $d -> $TASK (n=3)"
  python3 bench/run.py --task "$TASK" --runs 3 --arm treatment --skill-from "$R/$d" \
    || echo "run.py exited non-zero for $d"
  check_postponed
done
echo "### E13 PROBE DONE"
