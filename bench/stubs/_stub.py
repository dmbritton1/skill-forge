"""Blank top-level functions for an author-mode bench task.

A function keeps its signature and its existing docstring, byte for byte from
the source, so a stub reproduces what the historical author had in front of
them without anyone retyping it. A function with no docstring gets the one the
caller supplies. Functions are located through the AST, not a regex, so a
decorator or an unusual signature cannot shift the cut.
"""
import ast
import pathlib

RAISE = '    raise NotImplementedError("implement me")\n'


def _docstring_lines(node, lines):
    first = node.body[0]
    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)):
        return lines[first.lineno - 1:first.end_lineno]
    return None


def stub_functions(path, names, docstrings=None):
    docstrings = docstrings or {}
    path = pathlib.Path(path)
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    nodes = {n.name: n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
    missing = [n for n in names if n not in nodes]
    if missing:
        raise ValueError("no top-level function named %s in %s" % (missing, path))
    for name in sorted(names, key=lambda n: nodes[n].lineno, reverse=True):
        node = nodes[name]
        start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
        header = lines[start:node.body[0].lineno - 1]
        if name in docstrings:
            doc = docstrings[name].splitlines(keepends=True)
        else:
            doc = _docstring_lines(node, lines)
            if doc is None:
                raise ValueError("%s has no docstring and none was supplied" % name)
        lines[start:node.end_lineno] = header + doc + [RAISE]
    out = "".join(lines)
    ast.parse(out)
    path.write_text(out, encoding="utf-8")
