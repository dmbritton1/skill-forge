#!/usr/bin/env bash
# E15 stage D probe. Composition and order are pre-registered:
# docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md, section 3.
#
# Control x3, each delivered variant draft x3, E13's three skill drafts x3, in
# three interleaved rounds (bench/e15_read.py --order). Repeats follow round 3,
# at most 8. Spec amendment 4: a failed session never counts and is re-run in
# its place. At the session limit the script waits for the reset and goes on;
# after 3 failed sessions in a row it stops, and --resume continues the same
# batch. It stops on a void or mixed batch, on a void baseline draft (plan
# ruling 4), if the CLI version or HEAD changes, and on any reader output it
# does not recognise.
#
# Read with: python3 bench/e15_read.py --window <E15_START> -
# Usage: bash bench/e15_probe.sh [--dry-run | --resume <E15_START>]
set -u
export DISABLE_AUTOUPDATER=1  # a CLI update mid-batch would stop it (amendment 4)
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
DRY=0
START=""
case "${1:-}" in
  --dry-run) DRY=1 ;;
  --resume) START="${2:?--resume needs the batch E15_START}" ;;
  "") ;;
  *) echo "usage: bash bench/e15_probe.sh [--dry-run | --resume <E15_START>]"; exit 1 ;;
esac
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

CLI="$(claude --version)"
HEAD="$(git rev-parse HEAD)"
if [ -n "$START" ]; then
  ENVS="$(python3 bench/e15_read.py --window "$START" - --env)" || { echo "FATAL: could not read the batch's env"; exit 1; }
  if [ -n "$ENVS" ]; then
    [ "$(printf '%s\n' "$ENVS" | wc -l | tr -d ' ')" = 1 ] || { echo "$ENVS"; echo "FATAL: the batch is mixed"; exit 1; }
    case "$ENVS" in
      "$CLI|claude-opus-5|archive:$HEAD") ;;
      *) echo "batch: $ENVS"; echo "now:   $CLI|claude-opus-5|archive:$HEAD"
         echo "FATAL: the CLI or HEAD changed since the batch began -- restore them (npm i -g @anthropic-ai/claude-code@<version>, git checkout), then resume"; exit 1 ;;
    esac
  fi
fi

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed; CLI $CLI, HEAD ${HEAD:0:7}; a real run probes the allowance, then ${#ORDER[@]} sessions plus up to 8 repeats"
  exit 0
fi

allowance() {  # waits, re-probing every 10 minutes, until a session can run
  local out
  while :; do
    if out="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)"; then
      case "$out" in *limit*) ;; *) return 0 ;; esac
    fi
    echo "waiting ($(date +%H:%M)): $out"
    sleep 600
  done
}

allowance
[ -n "$START" ] || START="$(date +%Y-%m-%dT%H:%M:%S)"
echo "E15_START $START"
echo "resume with: bash bench/e15_probe.sh --resume $START"

FAILS=0
while :; do
  OUT="$(python3 bench/e15_read.py --window "$START" - 2>&1)" \
    || { echo "$OUT"; echo "STOP: the reader failed"; exit 1; }
  case "$OUT" in
    "batch: incomplete"*|"batch: complete"*) FAILS=0 ;;
    "batch: paused -- session limit"*) FAILS=0; echo "$OUT" | head -n 1; allowance ;;
    "batch: paused -- failed session"*)
      FAILS=$((FAILS + 1))
      if [ "$FAILS" -ge 3 ]; then
        echo "$OUT"; echo "STOP: 3 failed sessions in a row -- find the cause, then: bash bench/e15_probe.sh --resume $START"; exit 1
      fi
      sleep 120; allowance ;;
    "batch: void"*) echo "$OUT"; echo "STOP: the control resolved -- the batch is void"; exit 1 ;;
    "batch: mixed"*) echo "$OUT"; echo "STOP: the CLI, model or plugin commit changed mid-batch"; exit 1 ;;
    *) echo "$OUT"; echo "STOP: could not read the batch -- fix bench/e15_read.py, then resume"; exit 1 ;;
  esac
  if printf '%s\n' "$OUT" | grep -qE '^  baseline .* void$'; then
    echo "$OUT"; echo "STOP: a baseline draft voided -- d cannot be computed (plan ruling 4)"; exit 1
  fi
  NEXT="$(python3 bench/e15_read.py --window "$START" - --next 2>&1)" \
    || { echo "$NEXT"; echo "STOP: could not read the next run"; exit 1; }
  [ -n "$NEXT" ] || break
  known "$NEXT" || { echo "$NEXT"; echo "STOP: unexpected --next output"; exit 1; }
  [ "$(claude --version)" = "$CLI" ] || { echo "STOP: the CLI changed to $(claude --version) -- reinstall $CLI, then resume"; exit 1; }
  [ "$(git rev-parse HEAD)" = "$HEAD" ] || { echo "STOP: HEAD moved -- check out $HEAD, then resume"; exit 1; }
  echo "### $NEXT ($(date +%H:%M:%S))"
  ROWS="$(wc -l < bench/results.jsonl)"
  if [ "$NEXT" = "control" ]; then
    python3 bench/run.py --task "$TASK" --runs 1 --arm control --model claude-opus-5 \
      || echo "run.py exited non-zero for control"
  else
    python3 bench/run.py --task "$TASK" --runs 1 --arm treatment --model claude-opus-5 \
      --skill-from "$R/$NEXT" || echo "run.py exited non-zero for $NEXT"
  fi
  if [ "$(wc -l < bench/results.jsonl)" = "$ROWS" ]; then
    NOROW=$((${NOROW:-0} + 1))
    [ "$NOROW" -lt 3 ] || { echo "STOP: run.py wrote no row 3 times in a row -- find the cause, then: bash bench/e15_probe.sh --resume $START"; exit 1; }
    sleep 120; allowance
  else
    NOROW=0
  fi
done

echo "$OUT"
if ! printf '%s\n' "$OUT" | head -n 1 | grep -q '^batch: complete'; then
  echo "INCOMPLETE: runs still missing after 8 repeats -- record this batch as incomplete"
  exit 1
fi
echo "### E15 PROBE DONE"
