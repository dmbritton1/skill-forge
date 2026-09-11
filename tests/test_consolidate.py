"""Clustering and merging for /consolidate.
Run: python3 tests/test_consolidate.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import consolidate


def meta(name, command, bucket="unproven", kind="skill", scope="project",
         successes=0, last_used=None, fingerprints=None, symptoms=None):
    return {"name": name, "kind": kind, "scope": scope, "bucket": bucket,
            "successes": successes, "last_used": last_used,
            "path": "/store/%s/SKILL.md" % name, "command": command,
            "fingerprints": list(fingerprints or []),
            "symptoms": list(symptoms or [])}


def test_the_stored_command_arrives_wrapped_in_quotes():
    """save_skill writes `verification.command: "python3 tests/x.py"`, so the
    parsed value literally starts and ends with a double quote. Comparing raw
    values would still cluster, but the JSON a human reads would show the
    quotes -- and a skill quoted differently would not match one that is not.
    """
    assert consolidate.normalize_command('"python3 tests/x.py"') == "python3 tests/x.py"
    assert consolidate.normalize_command("  python3 tests/x.py  ") == "python3 tests/x.py"
    assert consolidate.normalize_command("'python3 tests/x.py'") == "python3 tests/x.py"


def test_an_absent_or_empty_command_normalizes_to_none():
    for empty in (None, "", "   ", '""'):
        assert consolidate.normalize_command(empty) is None, empty


def test_two_skills_sharing_a_command_cluster():
    a = meta("a", '"python3 tests/test_detect.py"')
    b = meta("b", '"python3 tests/test_detect.py"')
    cl, un = consolidate.clusters([a, b])
    assert len(cl) == 1, cl
    assert [m["name"] for m in cl[0]["members"]] == ["a", "b"], cl
    assert cl[0]["command"] == "python3 tests/test_detect.py", cl
    assert un == [], un


def test_different_commands_do_not_cluster():
    """The measured false negative, made explicit: these two are about the
    same bug and name the same test FILE, but one runs it through pytest.
    Parsing a path out of an arbitrary shell command would catch it and is
    deliberately not done -- a false positive merges two different bugs.
    """
    a = meta("a", '"python3 tests/test_detect.py"')
    b = meta("b", '"python3 -m pytest tests/test_detect.py -q"')
    cl, un = consolidate.clusters([a, b])
    assert cl == [], cl
    assert sorted(u["name"] for u in un) == ["a", "b"], un


def test_a_lone_skill_is_never_a_cluster():
    cl, un = consolidate.clusters([meta("a", '"python3 tests/x.py"')])
    assert cl == [], cl
    assert len(un) == 1 and un[0]["name"] == "a", un


def test_a_skill_with_no_command_is_unclustered_with_a_reason():
    """verification.command is optional for anti-skills (save_skill.py:145),
    so this is a normal library member, not a broken one."""
    cl, un = consolidate.clusters([meta("a", None, kind="antiskill"),
                                   meta("b", None, kind="antiskill")])
    assert cl == [], cl
    assert [u["reason"] for u in un] == ["no verification.command"] * 2, un


def test_clusters_never_cross_scope():
    a = meta("a", '"python3 tests/x.py"', scope="project")
    b = meta("b", '"python3 tests/x.py"', scope="global")
    cl, un = consolidate.clusters([a, b])
    assert cl == [], cl


def test_clusters_never_cross_kind():
    """A skill and an anti-skill are delivered by different paths and read by
    the model differently. Merging them would produce neither."""
    a = meta("a", '"python3 tests/x.py"', kind="skill")
    b = meta("b", '"python3 tests/x.py"', kind="antiskill")
    cl, un = consolidate.clusters([a, b])
    assert cl == [], cl


def test_a_singleton_reason_names_the_command():
    cl, un = consolidate.clusters([meta("solo", '"python3 tests/x.py"')])
    assert un[0]["reason"] == "only skill with this verification.command", un


if __name__ == "__main__":
    failures = 0
    for name in sorted(list(globals())):
        fn = globals()[name]
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS " + name)
            except Exception as err:
                failures += 1
                print("FAIL %s: %r" % (name, err))
    sys.exit(1 if failures else 0)
