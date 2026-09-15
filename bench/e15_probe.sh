#!/usr/bin/env bash
# E15 stage D probe. Composition and order are pre-registered:
# docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md, section 3.
#
# Control x3, each delivered variant draft x3, E13's three skill drafts x3, in
# three interleaved rounds (bench/e15_read.py --order). Repeats follow round 3,
# at most 8. The script stops on a postponed or void batch, on a void baseline
# draft (plan ruling 4), and on any reader output it does not recognise.
#
# Read with: python3 bench/e15_read.py --window <E15_START> -
# Usage: bash bench/e15_probe.sh [--dry-run]
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
TASK="sf-author-verdict-from"

python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty"; exit 1; }
if [ -n "$(git status --porcelain -- scripts hooks skills commands .claude-plugin)" ]; then
  echo "FATAL: uncommitted changes in the plugin under test"; exit 1
fi
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }
python3 bench/run.py --sandbox-check || { echo "FATAL: sandbox self-check failed"; exit 1; }
python3 bench/e15_prep.py --check-frozen || { echo "FATAL: E15 probe drafts not frozen, or the probe is not allowed"; exit 1; }

ORDER=()
while IFS= read -r arm; do
  [ -n "$arm" ] && ORDER+=("$arm")
done < <(python3 bench/e15_read.py --order)
[ "${#ORDER[@]}" -gt 0 ] || { echo "FATAL: could not read the probe order"; exit 1; }
echo "order (${#ORDER[@]} runs):"
printf '  %s\n' "${ORDER[@]}"

known() {  # $1: an arm name; true if it is "control" or appears in ORDER
  local a
  for a in "${ORDER[@]}"; do [ "$a" = "$1" ] && return 0; done
  return 1
}

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed; a real run probes the allowance, then ${#ORDER[@]} sessions plus up to 8 repeats"
  exit 0
fi

PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

START="$(date +%Y-%m-%dT%H:%M:%S)"
echo "E15_START $START"

check_read() {  # $1: reader output; stops the script on anything but a live batch
  case "$1" in
    "batch: incomplete"*|"batch: complete"*) ;;
    "batch: postponed"*) echo "$1"; echo "STOP: session limit -- re-run this whole batch later as one fresh batch"; exit 1 ;;
    "batch: void"*) echo "$1"; echo "STOP: the control resolved -- the batch is void"; exit 1 ;;
    *) echo "$1"; echo "STOP: could not read the batch -- fix bench/e15_read.py and re-run this whole batch later"; exit 1 ;;
  esac
  if printf '%s\n' "$1" | grep -qE '^  baseline .* void$'; then
    echo "$1"; echo "STOP: a baseline draft voided -- d cannot be computed (plan ruling 4)"; exit 1
  fi
}

run_one() {  # $1: control | a draft path from ORDER
  if [ "$1" = "control" ]; then
    python3 bench/run.py --task "$TASK" --runs 1 --arm control --model claude-opus-5 \
      || echo "run.py exited non-zero for control"
  else
    python3 bench/run.py --task "$TASK" --runs 1 --arm treatment --model claude-opus-5 \
      --skill-from "$R/$1" || echo "run.py exited non-zero for $1"
  fi
  local out
  out="$(python3 bench/e15_read.py --window "$START" - 2>&1)" \
    || { echo "$out"; echo "STOP: the reader failed"; exit 1; }
  check_read "$out"
}

for arm in "${ORDER[@]}"; do
  echo "### $arm"
  run_one "$arm"
done

EXTRA=0
while [ "$EXTRA" -lt 8 ]; do
  TODO_OUT="$(python3 bench/e15_read.py --window "$START" - --todo 2>&1)" \
    || { echo "$TODO_OUT"; echo "STOP: could not read the batch's remaining runs"; exit 1; }
  NEXT="$(printf '%s\n' "$TODO_OUT" | head -n 1)"
  [ -n "$NEXT" ] || break
  known "$NEXT" || { echo "$TODO_OUT"; echo "STOP: unexpected --todo output"; exit 1; }
  echo "### repeat $NEXT"
  run_one "$NEXT"
  EXTRA=$((EXTRA + 1))
done

FINAL_OUT="$(python3 bench/e15_read.py --window "$START" - 2>&1)" \
  || { echo "$FINAL_OUT"; echo "STOP: the reader failed on the final read"; exit 1; }
check_read "$FINAL_OUT"
echo "$FINAL_OUT"
if printf '%s\n' "$FINAL_OUT" | head -n 1 | grep -q '^batch: incomplete'; then
  echo "INCOMPLETE: runs still missing after 8 repeats -- record this batch as incomplete and re-run it whole later"
  exit 1
fi
echo "### E15 PROBE DONE"
