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


def test_the_highest_bucket_member_lends_its_name():
    """Organic history is keyed by NAME and Tier A verdicts by content hash,
    so inheriting the best name keeps the successes and loses only the
    verdicts -- `working` rather than `unproven`."""
    ms = [meta("low", "c", bucket="unproven"),
          meta("high", "c", bucket="trusted"),
          meta("mid", "c", bucket="working")]
    assert consolidate.inherit_name(ms) == "high", ms


def test_successes_break_a_bucket_tie():
    ms = [meta("few", "c", bucket="working", successes=1),
          meta("many", "c", bucket="working", successes=4)]
    assert consolidate.inherit_name(ms) == "many"


def test_recency_breaks_a_successes_tie():
    ms = [meta("old", "c", bucket="working", successes=2,
               last_used="2026-01-01T00:00:00"),
          meta("new", "c", bucket="working", successes=2,
               last_used="2026-09-01T00:00:00")]
    assert consolidate.inherit_name(ms) == "new"


def test_a_never_used_member_loses_to_a_used_one_on_recency():
    """last_used is None for a skill no session has ever fired. That must sort
    as older than any real timestamp, not crash and not win."""
    ms = [meta("never", "c", bucket="working", successes=2, last_used=None),
          meta("once", "c", bucket="working", successes=2,
               last_used="2026-01-01T00:00:00")]
    assert consolidate.inherit_name(ms) == "once"


def test_the_final_tie_breaks_on_name_so_the_choice_is_deterministic():
    """Otherwise the inherited name depends on index order, and the same
    library proposes a different merge on two consecutive runs."""
    ms = [meta("zebra", "c"), meta("apple", "c")]
    assert consolidate.inherit_name(ms) == "apple"
    assert consolidate.inherit_name(list(reversed(ms))) == "apple"


def test_an_unknown_bucket_never_outranks_a_known_one():
    ms = [meta("weird", "c", bucket=""), meta("plain", "c", bucket="unproven")]
    assert consolidate.inherit_name(ms) == "plain"


def test_patterns_are_unioned_with_order_preserved_and_duplicates_dropped():
    ms = [meta("a", "c", fingerprints=["x", "y"]),
          meta("b", "c", fingerprints=["y", "z"])]
    assert consolidate.merge_patterns(ms, "fingerprints") == ["x", "y", "z"]


def test_symptoms_union_the_same_way():
    ms = [meta("a", "c", symptoms=["boom"]), meta("b", "c", symptoms=["boom", "bang"])]
    assert consolidate.merge_patterns(ms, "symptoms") == ["boom", "bang"]


def test_a_member_missing_the_field_entirely_is_skipped_not_fatal():
    ms = [{"name": "a"}, meta("b", "c", fingerprints=["x"])]
    assert consolidate.merge_patterns(ms, "fingerprints") == ["x"]


def test_the_proposal_names_what_to_keep_and_unions_the_patterns():
    ms = [meta("a", '"python3 tests/x.py"', bucket="working",
               fingerprints=["x"], symptoms=["boom"]),
          meta("b", '"python3 tests/x.py"', bucket="unproven",
               fingerprints=["y"], symptoms=["boom"])]
    p = consolidate.proposal(ms)
    assert len(p["clusters"]) == 1, p
    c = p["clusters"][0]
    assert c["keep"] == "a", c
    assert c["fingerprints"] == ["x", "y"], c
    assert c["symptoms"] == ["boom"], c
    assert [m["name"] for m in c["members"]] == ["a", "b"], c


def test_the_proposal_is_json_serialisable():
    """cmd_propose prints it for the command file to read back."""
    import json
    ms = [meta("a", '"python3 tests/x.py"'), meta("b", '"python3 tests/x.py"')]
    json.dumps(consolidate.proposal(ms))


def test_filtering_by_name_keeps_only_that_skills_cluster():
    ms = [meta("a", '"python3 tests/x.py"'), meta("b", '"python3 tests/x.py"'),
          meta("c", '"python3 tests/y.py"'), meta("d", '"python3 tests/y.py"')]
    p = consolidate.proposal(ms, name="c")
    assert len(p["clusters"]) == 1, p
    assert sorted(m["name"] for m in p["clusters"][0]["members"]) == ["c", "d"]


def test_filtering_by_a_name_in_no_cluster_returns_nothing():
    ms = [meta("solo", '"python3 tests/x.py"')]
    p = consolidate.proposal(ms, name="solo")
    assert p["clusters"] == [], p


def test_members_carry_only_what_the_command_file_needs():
    """The proposal is printed to a model. Skill BODIES are untrusted data and
    must not ride along in it."""
    ms = [meta("a", '"python3 tests/x.py"'), meta("b", '"python3 tests/x.py"')]
    m = consolidate.proposal(ms)["clusters"][0]["members"][0]
    assert set(m) == {"name", "bucket", "successes", "path"}, m


def _with_fake_archive(fn):
    """Replace library.cmd_archive; return (result, names it was called with)."""
    calls = []
    real = consolidate.library.cmd_archive
    consolidate.library.cmd_archive = lambda n: (calls.append(n), 0)[1]
    try:
        return fn(), calls
    finally:
        consolidate.library.cmd_archive = real


def test_retire_never_archives_the_kept_name():
    """cmd_archive moves a store directory BY NAME. The merged skill lives at
    the kept name, so archiving it would move the merge itself."""
    rc, calls = _with_fake_archive(
        lambda: consolidate.cmd_retire("a", ["a", "b", "c"]))
    assert calls == ["b", "c"], calls
    assert rc == 0, rc


def test_retire_with_nothing_to_do_is_not_an_error():
    rc, calls = _with_fake_archive(lambda: consolidate.cmd_retire("a", ["a"]))
    assert calls == [], calls
    assert rc == 0, rc


def test_a_failing_archive_is_reported_and_the_rest_still_run():
    """Stopping at the first failure would leave the library in a state nobody
    chose: merged skill saved, some members retired, the rest silently not."""
    calls = []

    def fake(n):
        calls.append(n)
        return 1 if n == "b" else 0

    real = consolidate.library.cmd_archive
    consolidate.library.cmd_archive = fake
    try:
        rc = consolidate.cmd_retire("a", ["b", "c"])
    finally:
        consolidate.library.cmd_archive = real
    assert calls == ["b", "c"], calls
    assert rc == 1, rc


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
