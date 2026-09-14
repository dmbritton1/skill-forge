#!/usr/bin/env bash
# E13 outcome test for trap 2. Composition is pre-registered:
# docs/superpowers/specs/2026-09-13-e13-author-traps-design.md, section 8.
#
# Library: the consolidated seven plus the trap's first qualifying draft.
# Two arms of 6, old first: the plugin as archived at 06885c0, then at 9cbb472,
# each extracted by run.snapshot_plugin and passed with --plugin-dir. Run it only
# after the probe batch read "working" -- section 6.1 makes that a condition.
# A session refused at the session limit stops the script; re-run it whole.
#
# Read with: python3 bench/e13_outcome_read.py --trap <trap> --window <OUTCOME_START> -
# Usage: bash bench/e13_outcome.sh --trap C [--dry-run]
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
[ -n "$TRAP" ] || { echo "usage: bash bench/e13_outcome.sh --trap C [--dry-run]"; exit 1; }
Q="bench/distilled/$TRAP/qualification.json"
[ -f "$Q" ] || { echo "FATAL: $Q missing"; exit 1; }

python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty"; exit 1; }
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }
# Sandbox spec section 4.4: zero sessions, before the first one.
python3 bench/run.py --sandbox-check || { echo "FATAL: sandbox self-check failed"; exit 1; }

TASK="$(python3 -c "import json; print(json.load(open('$Q'))['task'])")"
DRAFT="$(python3 -c "import json; print(json.load(open('$Q'))['first_qualifying'] or '')")"
[ -n "$DRAFT" ] || { echo "FATAL: trap $TRAP has no qualifying draft -- it cannot be trap 2 (section 6.1)"; exit 1; }
PLUS=()
while IFS= read -r p; do
  [ -n "$p" ] && PLUS+=(--plus-skill "$R/$p")
done < <(python3 -c "
import sys; sys.path[:0] = ['scripts', 'bench']; import budget_sweep as bs
for e in bs.seven:
    print(e['_path'])
")
[ "${#PLUS[@]}" -eq 14 ] || { echo "FATAL: expected the consolidated seven, got $(( ${#PLUS[@]} / 2 ))"; exit 1; }

SNAP="${SKILLFORGE_BENCH_WORK:-/tmp/skillforge-bench}/snapshots"
for ref in 06885c0 9cbb472; do
  python3 -c "import sys; sys.path.insert(0, 'bench'); import run; print(run.snapshot_plugin('$ref', '$SNAP/$ref'))" \
    || { echo "FATAL: snapshot $ref failed"; exit 1; }
done
echo "task: $TASK"
echo "draft: $DRAFT"
echo "library: the consolidated seven + draft"

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed and both snapshots built; a real run probes the allowance, then 6 old and 6 new"
  exit 0
fi

PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

START="$(date +%Y-%m-%dT%H:%M:%S)"
echo "OUTCOME_START $START"
for ref in 06885c0 9cbb472; do
  echo "### arm $ref (n=6)"
  python3 bench/run.py --task "$TASK" --runs 6 --arm treatment --skill-from "$R/$DRAFT" \
    "${PLUS[@]}" --plugin-dir "$SNAP/$ref" || echo "run.py exited non-zero for arm $ref"
  OUT="$(python3 bench/e13_outcome_read.py --trap "$TRAP" --window "$START" - 2>&1)"
  echo "$OUT"
  case "$OUT" in
    "batch: postponed"*) echo "STOP: session limit -- re-run this whole batch later"; exit 1 ;;
  esac
done
echo "### E13 OUTCOME DONE"
