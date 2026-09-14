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
