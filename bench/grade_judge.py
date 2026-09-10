#!/usr/bin/env python3
"""The judge half of graded scoring (spec §3.2).

SPENDS REAL MODEL CALLS -- one `claude -p` turn per artifact. Never run this
from a test; tests/ is forbidden from invoking a model.

Scores what an assertion cannot. Reported ALONGSIDE the probe score, never
merged into it: a disagreement between the halves is the signal, and merging
them is how it would be hidden.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import validate

# Every row in bench/results.jsonl carries model: claude-opus-5 (bench/run.py
# pins it); the judge must grade with the same model, not validate.py's
# unrelated sonnet default, and record which model judged the row.
JUDGE_MODEL = "claude-opus-5"

CRITERIA = {
    "explicit_unknown":
        "Is the unknown-versus-absent distinction explicit -- a named branch,"
        " an early return, or a comment saying which is which -- rather than"
        " something that merely falls out of the control flow?",
    "bounds_documented":
        "Where a bound or cap is applied, is it explained at the point of use,"
        " rather than appearing as a bare constant?",
    "visible_degradation":
        "On unexpected input, does the code fail or degrade visibly rather"
        " than silently returning a confident answer?",
}

TARGET = {
    "sf-author-response-text": ("detect.py", "response_text"),
    "sf-author-fingerprint-preexisting": ("retrieve.py", "fingerprint_preexisting"),
}


def target_for(task):
    for base, spec in TARGET.items():
        if task == base or task.startswith(base + "-"):
            return spec
    return None


def extract(clone, task):
    """The authored function's source, or None."""
    spec = target_for(task)
    if not spec:
        return None
    fname, func = spec
    try:
        src = (pathlib.Path(clone) / "scripts" / fname).read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^def %s\(.*?\n(?:.*\n)*?(?=^def |\Z)" % re.escape(func),
                  src, re.M)
    return m.group(0) if m else None


def build_prompt(source):
    lines = ["Judge this Python function against each criterion below.",
             "Answer ONLY with a JSON object mapping every criterion key to"
             " true or false. No prose, no code fences.", ""]
    for key, question in CRITERIA.items():
        lines.append("%s: %s" % (key, question))
    lines += ["", "```python", source, "```"]
    return "\n".join(lines)


def parse(text):
    """{criterion: bool}, or None if unreadable or incomplete.

    A partial verdict is rejected rather than scored: a fraction over a
    denominator the model chose is not a measurement.
    """
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        got = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(got, dict):
        return None
    if set(got) != set(CRITERIA):
        return None
    if not all(isinstance(v, bool) for v in got.values()):
        return None
    return got


def summarize(verdict):
    """judge_ok distinguishes 'could not judge' from 'judged, criteria unmet'.

    run_model returns None for a timeout, a crash AND a session limit alike.
    A refused session is not a verdict; this repo has already archived one as
    a real result and then locked it.
    """
    if verdict is None:
        return {"judge_ok": False, "judge_score": None, "judge_detail": {},
                "judge_model": JUDGE_MODEL}
    met = sum(1 for v in verdict.values() if v)
    return {"judge_ok": True, "judge_score": met / len(verdict),
            "judge_detail": verdict, "judge_model": JUDGE_MODEL}


def judge(clone, task):
    source = extract(clone, task)
    if source is None:
        return summarize(None)
    text = validate.run_model(build_prompt(source), cwd=str(clone), model=JUDGE_MODEL)
    return summarize(parse(text))


if __name__ == "__main__":
    print(__doc__)
