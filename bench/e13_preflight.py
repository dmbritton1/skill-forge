#!/usr/bin/env python3
"""E13 pre-flight: build each candidate's author task and decide its graded tests.

docs/superpowers/specs/2026-09-13-e13-author-traps-design.md, section 2.

Zero sessions. Each candidate's fix-commit test file runs three ways against the
parent commit's code: with the stub, with the parent's original function (the
historical bug), and with the fix's changed definitions transplanted in. The
graded set is every test that fails under the stub and passes with the fix.
Only a candidate that passes every validity rule is written into
bench/tasks.json. An entry with an empty or unvalidated fail_to_pass grades
nothing, and score() reads that as resolved.
"""
import ast
import re
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent

SPEC = "docs/superpowers/specs/2026-09-13-e13-author-traps-design.md"

CANDIDATES = {
    "C": {"id": "sf-author-verdict-from", "fix": "c0d7d88", "source": "scripts/validate.py",
          "test_path": "tests/test_validate.py", "stub": "bench/stubs/stub_verdict_from.py",
          "functions": ["verdict_from"], "own_runner": True, "verbatim_docstring": True},
    "D": {"id": "sf-author-transcript-slice", "fix": "521f609", "source": "scripts/draft.py",
          "test_path": "tests/test_draft.py", "stub": "bench/stubs/stub_transcript_slice.py",
          "functions": ["transcript_slice"], "own_runner": False, "verbatim_docstring": True},
    "E": {"id": "sf-author-store-dir", "fix": "06173b0", "source": "scripts/save_skill.py",
          "test_path": "tests/test_save_skill.py", "stub": "bench/stubs/stub_store_dir.py",
          "functions": ["store_dir", "native_dir"], "own_runner": True,
          "verbatim_docstring": False},
}

# E13 §5: the repair task each survivor is distilled from.
REPAIR_IDS = {"C": "sf-repair-verdict-from"}

RESULT_RX = re.compile(r"^(PASS|FAIL) (test_\w+)")


def _top_level(src):
    """({name: (start, end, text)} for defs and classes, [(start, end, text)] for imports)."""
    lines = src.splitlines(keepends=True)
    defs, imports = {}, []
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            defs[node.name] = (start, node.end_lineno, "".join(lines[start:node.end_lineno]))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append((node.lineno - 1, node.end_lineno,
                            "".join(lines[node.lineno - 1:node.end_lineno])))
    return defs, imports


def changed_definitions(parent_src, fix_src):
    pdefs, _ = _top_level(parent_src)
    fdefs, _ = _top_level(fix_src)
    return sorted(n for n, (_, _, text) in fdefs.items()
                  if n not in pdefs or pdefs[n][2] != text)


def transplant(parent_src, fix_src):
    """Parent source carrying every definition and import the fix added or changed.

    New definitions go directly before the first replaced one, so a helper sits
    beside its caller. Returns (source, transplanted names).
    """
    # ponytail: definitions and imports only. A fix that changes a module-level
    # constant is not carried; run 3 then fails, and the pre-flight reports it.
    names = changed_definitions(parent_src, fix_src)
    if not names:
        return parent_src, []
    pdefs, pimports = _top_level(parent_src)
    fdefs, fimports = _top_level(fix_src)
    lines = parent_src.splitlines(keepends=True)
    edits = [(pdefs[n][0], pdefs[n][1], fdefs[n][2]) for n in names if n in pdefs]
    new = sorted((n for n in names if n not in pdefs), key=lambda n: fdefs[n][0])
    if new:
        anchor = min((pdefs[n][0] for n in names if n in pdefs), default=len(lines))
        edits.append((anchor, anchor,
                      "".join(fdefs[n][2].rstrip("\n") + "\n\n\n" for n in new)))
    have = {text.strip() for _, _, text in pimports}
    added = [text for _, _, text in fimports if text.strip() not in have]
    if added:
        at = max((end for _, end, _ in pimports), default=0)
        edits.append((at, at, "".join(added)))
    # Bottom-up, and a replacement before an insertion at the same line, so no
    # edit shifts the line numbers of one still to come.
    for start, end, text in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        lines[start:end] = [text]
    out = "".join(lines)
    ast.parse(out)
    return out, names


def test_names(src):
    return {n.name for n in ast.parse(src).body
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


def parse_results(stdout):
    out = {}
    for line in stdout.splitlines():
        m = RESULT_RX.match(line.strip())
        if m:
            out[m.group(2)] = m.group(1) == "PASS"
    return out


def assess(stub, original, fix, fix_added, docstring_ok=True):
    """(graded tests, problems) under spec section 2.1. No problems means valid."""
    graded = sorted(t for t in fix if fix[t] is True and stub.get(t) is False)
    problems = []
    if not graded:
        problems.append("no graded tests: nothing fails with the stub and passes with the fix")
    unsatisfiable = sorted(t for t in fix_added if fix.get(t) is not True)
    if unsatisfiable:
        problems.append("tests the fix added do not pass with the fix transplanted: %s"
                        % unsatisfiable)
    if not any(original.get(t) is False for t in fix_added if t in graded):
        problems.append("the historical bug fails none of the graded tests the fix added")
    regressions = sorted(t for t in graded
                         if t not in fix_added and original.get(t) is not True)
    if regressions:
        problems.append("the historical function fails graded tests the fix did not add: %s"
                        % regressions)
    if not docstring_ok:
        problems.append("the stub's docstring differs from the parent's")
    return graded, problems


def signatures(src, names):
    nodes = {n.name: n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
    return ["%s(%s)" % (n, ast.unparse(nodes[n].args)) for n in names]


def author_prompt(source, sigs, test_path):
    """The existing author-task template, verbatim, with names substituted."""
    tail = ("do not modify anything under tests/. When you are done, run `python3 %s` "
            "and make sure you have not broken any test that was passing before your "
            "change." % test_path)
    if len(sigs) == 1:
        return ("%s has a function `%s` whose body raises NotImplementedError. Read its "
                "docstring for the contract and implement it. Do not change its signature, "
                "and %s" % (source, sigs[0], tail))
    return ("%s has functions %s whose bodies raise NotImplementedError. Read their "
            "docstrings for the contract and implement them. Do not change their "
            "signatures, and %s"
            % (source, " and ".join("`%s`" % s for s in sigs), tail))


def task_entry(letter, cand, graded, sigs):
    test_cmd = ("python3 %s" % cand["test_path"] if cand["own_runner"] else
                "python3 {root}/bench/run_named_tests.py %s %s"
                % (cand["test_path"], " ".join(graded)))
    return {
        "id": cand["id"],
        "mode": "author",
        "repo": "{root}",
        "fix_commit": cand["fix"],
        "test_path": cand["test_path"],
        "test_cmd": test_cmd,
        "setup_cmd": "true",
        "stub_cmd": "python3 {root}/%s" % cand["stub"],
        "fail_to_pass": list(graded),
        "prompt": author_prompt(cand["source"], sigs, cand["test_path"]),
        "skill": None,
        "skill_source_commit": None,
        "selection_rule": ("E13 trap %s (%s). No skill yet: control screen only until "
                           "distilled. Graded tests decided by bench/e13_preflight.py."
                           % (letter, SPEC)),
    }


def upsert(cfg, entry):
    for i, task in enumerate(cfg["tasks"]):
        if task["id"] == entry["id"]:
            cfg["tasks"][i] = entry
            return cfg
    cfg["tasks"].append(entry)
    return cfg


def repair_prompt(test_path):
    """The existing repair-task template, verbatim, with the test file substituted."""
    return ("The test suite %s has failing tests. Run `python3 %s` to see which ones "
            "fail, then fix the source under scripts/ so that every test passes. Do not "
            "modify anything under tests/ - the tests are correct and describe the "
            "intended behavior. When you are done, run the test command again to confirm."
            % (test_path, test_path))


def repair_graded(original, fix_added):
    """Spec section 5: the fix-added tests the historical function fails."""
    return sorted(t for t in fix_added if original.get(t) is False)


def repair_entry(letter, cand, graded):
    assert cand["own_runner"], "a repair task grades with the file's own runner"
    return {
        "id": REPAIR_IDS[letter],
        "mode": "repair",
        "repo": "{root}",
        "fix_commit": cand["fix"],
        "test_path": cand["test_path"],
        "test_cmd": "python3 %s" % cand["test_path"],
        "setup_cmd": "true",
        "fail_to_pass": list(graded),
        "prompt": repair_prompt(cand["test_path"]),
        "skill": None,
        "skill_source_commit": None,
        "selection_rule": ("E13 trap %s repair task, for distillation only (%s section 5). "
                           "Graded: the fix-added tests the historical function fails, "
                           "decided by bench/e13_preflight.py --repair." % (letter, SPEC)),
    }


def docstrings_match(stubbed_src, parent_src, names):
    """True if every named function carries the same raw docstring in both."""
    def docs(src):
        nodes = {n.name: n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
        return {n: ast.get_docstring(nodes[n], clean=False) if n in nodes else None
                for n in names}
    return docs(stubbed_src) == docs(parent_src)


def _git(*args):
    return subprocess.run(["git", *args], cwd=str(REPO_ROOT), capture_output=True,
                          text=True, check=True).stdout


def run_variant(cand, variant, work):
    """Prepare one clone at the fix's parent and run its fix-commit tests.

    variant is "stub" (stub applied, then the hidden tests), "original" (the
    parent's own code with the fix's tests), or "fix" (the fix's changed
    definitions transplanted in). Returns ({test: passed}, clone path).
    """
    import run as bench_run
    task = {"id": "e13pf-%s-%s" % (cand["id"], variant), "repo": str(REPO_ROOT),
            "fix_commit": cand["fix"], "test_path": cand["test_path"],
            "setup_cmd": "true", "mode": "author" if variant == "stub" else "repair",
            "stub_cmd": "python3 %s" % (REPO_ROOT / cand["stub"])}
    dest = Path(work) / task["id"]
    bench_run.prepare(task, dest)
    if variant == "stub":
        bench_run.apply_hidden_tests(task, dest)
    elif variant == "fix":
        src = dest / cand["source"]
        fixed, _ = transplant(src.read_text(encoding="utf-8"),
                              _git("show", "%s:%s" % (cand["fix"], cand["source"])))
        src.write_text(fixed, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("SKILLFORGE_")}
    r = bench_run.sh("python3 %s %s" % (ROOT / "run_named_tests.py", cand["test_path"]),
                     cwd=dest, timeout=900, env=env)
    return parse_results(r.stdout), dest


def _summary(results):
    return "%d pass / %d fail" % (sum(results.values()), sum(not v for v in results.values()))


def write_tasks(entries):
    path = ROOT / "tasks.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for entry in entries:
        upsert(cfg, entry)
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print("wrote %s into bench/tasks.json" % sorted(e["id"] for e in entries))


def repair_main(letters, write):
    import run as bench_run
    work = Path(os.path.realpath(tempfile.mkdtemp(prefix="e13-repair-")))
    bench_run.WORK = work
    entries = []
    try:
        for letter in letters:
            cand = CANDIDATES[letter]
            fix_added = (test_names(_git("show", "%s:%s" % (cand["fix"], cand["test_path"])))
                         - test_names(_git("show", "%s~1:%s" % (cand["fix"], cand["test_path"]))))
            original, _ = run_variant(cand, "original", work)
            graded = repair_graded(original, fix_added)
            print("=== %s repair  %s  graded (%d): %s"
                  % (letter, REPAIR_IDS[letter], len(graded), graded))
            if graded:
                entries.append(repair_entry(letter, cand, graded))
            else:
                print("  INVALID: the historical function fails no fix-added test")
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
    if write and entries:
        write_tasks(entries)
    return 0 if len(entries) == len(letters) else 1


def main(argv=None):
    import run as bench_run
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", choices=sorted(CANDIDATES))
    ap.add_argument("--write", action="store_true",
                    help="write valid candidates into bench/tasks.json")
    ap.add_argument("--repair", action="store_true", help="build the section 5 repair task instead")
    args = ap.parse_args(argv)
    letters = args.only or sorted(CANDIDATES)
    if args.repair:
        unknown = [l for l in letters if l not in REPAIR_IDS]
        if unknown:
            ap.error("no repair task defined for %s" % unknown)
        return repair_main(letters, args.write)
    work = Path(os.path.realpath(tempfile.mkdtemp(prefix="e13-preflight-")))
    bench_run.WORK = work
    valid = {}
    try:
        for letter in letters:
            cand = CANDIDATES[letter]
            parent_src = _git("show", "%s~1:%s" % (cand["fix"], cand["source"]))
            fix_added = (test_names(_git("show", "%s:%s" % (cand["fix"], cand["test_path"])))
                         - test_names(_git("show", "%s~1:%s" % (cand["fix"], cand["test_path"]))))
            stub, stub_dest = run_variant(cand, "stub", work)
            original, _ = run_variant(cand, "original", work)
            fix, _ = run_variant(cand, "fix", work)
            doc_ok = (not cand["verbatim_docstring"]) or docstrings_match(
                (stub_dest / cand["source"]).read_text(encoding="utf-8"),
                parent_src, cand["functions"])
            graded, problems = assess(stub, original, fix, fix_added, doc_ok)
            print("=== %s  %s  (fix %s)" % (letter, cand["id"], cand["fix"]))
            print("  stub:     %s" % _summary(stub))
            print("  original: %s" % _summary(original))
            print("  fix:      %s" % _summary(fix))
            print("  tests the fix added: %s" % sorted(fix_added))
            print("  graded (%d): %s" % (len(graded), graded))
            if problems:
                print("  INVALID: " + "; ".join(problems))
            else:
                print("  VALID")
                valid[letter] = task_entry(letter, cand, graded,
                                           signatures(parent_src, cand["functions"]))
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
    if args.write and valid:
        write_tasks(valid.values())
    return 0 if len(valid) == len(letters) else 1


if __name__ == "__main__":
    sys.exit(main())
