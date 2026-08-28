"""Tests for trust-gated native sync. Run: python3 tests/test_sync.py"""
import datetime
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ledger
import sync
import trust

# sync() schedules one executable validation run per session (Task 8). No
# suite may spawn a real subprocess, so the seam is stubbed inert here for
# every test in this file; the spawn test below installs its own stub over
# the top of this one and restores it (not the real Popen-backed function).
# The real function is saved first: the env-inspection tests at the bottom
# call it directly (with subprocess.Popen itself stubbed out) to check what
# it builds, and would otherwise see this inert lambda instead.
_REAL_SPAWN_VALIDATION = sync._spawn_validation
sync._spawn_validation = lambda name, mode: None

SKILL = """---
name: %s
kind: skill
description: A thing. Do NOT use otherwise.
---
## Procedure
1. Do it.
"""


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


def put_skill(base, name, text=None):
    d = base / ".claude" / "skillforge" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    md.write_text(text if text is not None else SKILL % name, encoding="utf-8")
    return md


ANTISKILL = """---
name: %s
kind: antiskill
description: A trap. Do NOT use otherwise.
symptoms:
  - "WidgetFlushedError: the widget was already flushed"
fingerprints:
  - "await widget.flush({ force: true })"
---
## Trap
t
## Symptom
s
## Cause
c
## Fix
f
"""

SKILL_WITH_TRIGGERS = """---
name: %s
kind: skill
description: A thing. Do NOT use otherwise.
verification.command: "npx stripe trigger payment_intent.succeeded"
fingerprints:
  - "express.raw({type: 'application/json'})"
---
## Procedure
1. Do it.
## Verification
Run the command.
"""


def put_antiskill(base, name, text=None):
    d = base / ".claude" / "skillforge" / "antiskills" / name
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    md.write_text(text if text is not None else ANTISKILL % name, encoding="utf-8")
    return md


def read_json(home, filename):
    import json
    return json.loads((home / ".claude" / "skillforge" / filename).read_text(encoding="utf-8"))


def native_md(base, name):
    return base / ".claude" / "skills" / "skillforge-hot" / name / "SKILL.md"


def test_trusted_skill_materialized():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")   # hot-eligible: this test measures materialization, not the gate
        counts = sync.sync()
        assert counts["materialized"] == 1 and counts["quarantined"] == 0
        assert native_md(home, "alpha").read_text(encoding="utf-8") == SKILL % "alpha"
    in_sandbox(check)


def test_untrusted_skill_quarantined_not_materialized():
    def check(home):
        put_skill(home, "alpha")
        counts = sync.sync()
        assert counts["quarantined"] == 1 and counts["materialized"] == 0
        assert not native_md(home, "alpha").exists()
    in_sandbox(check)


def test_modified_store_evicts_native():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")   # hot-eligible: this test measures eviction, not the gate
        sync.sync()
        assert native_md(home, "alpha").exists()
        md.write_text(md.read_text(encoding="utf-8") + "\nEXTRA LINE\n", encoding="utf-8")
        counts = sync.sync()
        assert counts["quarantined"] == 1 and counts["evicted"] == 1
        assert not native_md(home, "alpha").exists()
    in_sandbox(check)


def test_orphan_native_dir_evicted():
    def check(home):
        stale = home / ".claude" / "skills" / "skillforge-hot" / "ghost"
        stale.mkdir(parents=True)
        (stale / "SKILL.md").write_text("boo", encoding="utf-8")
        counts = sync.sync()
        assert counts["evicted"] == 1
        assert not stale.exists()
    in_sandbox(check)


def test_project_root_store_synced():
    def check(home):
        proj = home / "myrepo"
        md = put_skill(proj, "beta")
        trust.record("beta", md.read_text(encoding="utf-8"), "self")
        earn_success("beta")   # hot-eligible: this test measures project-root sync, not the gate
        counts = sync.sync(project_root=str(proj))
        assert counts["materialized"] == 1
        assert native_md(proj, "beta").exists()
    in_sandbox(check)


def test_corrupt_trust_json_quarantines_and_exits_zero():
    def check(home):
        put_skill(home, "alpha")
        reg = home / ".claude" / "skillforge" / "trust.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text("{not json", encoding="utf-8")
        rc = sync.main([])
        assert rc == 0
        assert not native_md(home, "alpha").exists()
    in_sandbox(check)


def test_sync_is_idempotent():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")   # hot-eligible: this test measures idempotency, not the gate
        first = sync.sync()
        second = sync.sync()
        assert first["materialized"] == second["materialized"] == 1
        assert second["evicted"] == 0
    in_sandbox(check)


def read_index(home):
    import json
    return json.loads((home / ".claude" / "skillforge" / "index.json").read_text(encoding="utf-8"))


def with_budget(value, fn):
    old = os.environ.get("SKILLFORGE_HOT_BUDGET")
    os.environ["SKILLFORGE_HOT_BUDGET"] = value
    try:
        fn()
    finally:
        if old is None:
            del os.environ["SKILLFORGE_HOT_BUDGET"]
        else:
            os.environ["SKILLFORGE_HOT_BUDGET"] = old


def test_hot_budget_overflow_goes_warm():
    def check(home):
        for name in ("alpha", "beta"):
            md = put_skill(home, name)
            trust.record(name, md.read_text(encoding="utf-8"), "self")
        # Both are hot-ELIGIBLE (the gate is not what this test measures);
        # beta outranks alpha on bucket, so the single slot is beta's.
        earn_success("alpha", session="s1")             # working
        earn_success("beta", session="s1")               # trusted
        earn_success("beta", session="s2")

        def run():
            counts = sync.sync()
            tiers = {e["name"]: e["tier"] for e in read_index(home)["entries"]}
            assert tiers == {"beta": "hot", "alpha": "warm"}
            assert native_md(home, "beta").exists()
            assert not native_md(home, "alpha").exists()
            assert counts["materialized"] == 1
        with_budget("10", run)
    in_sandbox(check)


def test_index_contains_trusted_only_with_paths():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")   # hot-eligible: this test measures index contents, not the gate
        put_skill(home, "gamma")  # never recorded -> quarantined
        sync.sync()
        idx = read_index(home)
        names = [e["name"] for e in idx["entries"]]
        assert names == ["alpha"]
        e = idx["entries"][0]
        assert e["tier"] == "hot" and e["kind"] == "skill" and e["scope"] == "global"
        assert e["root"] == str(home)
        assert pathlib.Path(e["path"]).is_file()
        assert e["description"].startswith("A thing.")
    in_sandbox(check)


def test_stale_session_state_cleanup():
    def check(home):
        import time
        d = home / ".claude" / "skillforge" / "state"
        d.mkdir(parents=True)
        old = d / "session-old.json"
        new = d / "session-new.json"
        old.write_text("[]", encoding="utf-8")
        new.write_text("[]", encoding="utf-8")
        stale = time.time() - 8 * 86400
        os.utime(old, (stale, stale))
        sync.sync()
        assert not old.exists()
        assert new.exists()
    in_sandbox(check)


def test_project_root_recorded_resolved():
    def check(home):
        import json, os
        proj = home / "myrepo"
        md = put_skill(proj, "beta")
        trust.record("beta", md.read_text(encoding="utf-8"), "self")
        old = os.getcwd()
        os.chdir(str(proj))
        try:
            sync.sync(project_root=".")
        finally:
            os.chdir(old)
        idx = json.loads((home / ".claude" / "skillforge" / "index.json").read_text(encoding="utf-8"))
        roots = {e["name"]: e["root"] for e in idx["entries"]}
        assert pathlib.Path(roots["beta"]).is_absolute()
        assert pathlib.Path(roots["beta"]) == proj.resolve()
    in_sandbox(check)


def test_triggers_compiled_from_trusted_skills():
    def check(home):
        md = put_antiskill(home, "widget-trap")
        trust.record("widget-trap", md.read_text(encoding="utf-8"), "self")
        md2 = put_skill(home, "stripe-hook", SKILL_WITH_TRIGGERS % "stripe-hook")
        trust.record("stripe-hook", md2.read_text(encoding="utf-8"), "self")
        sync.sync()
        trig = read_json(home, "triggers.json")
        assert [s["skill"] for s in trig["symptoms"]] == ["widget-trap"]
        assert trig["symptoms"][0]["tokens"] == [
            "widgetflushederror", "the", "widget", "was", "already", "flushed"]
        assert trig["symptoms"][0]["path"] == str(md)
        assert trig["symptoms"][0]["root"] == str(home)
        assert [v["skill"] for v in trig["verifications"]] == ["stripe-hook"]
        assert trig["verifications"][0]["tokens"] == [
            "npx", "stripe", "trigger", "payment_intent", "succeeded"]
    in_sandbox(check)


def test_quarantined_antiskill_symptoms_excluded():
    def check(home):
        put_antiskill(home, "widget-trap")   # never trusted
        sync.sync()
        trig = read_json(home, "triggers.json")
        assert trig["symptoms"] == []
    in_sandbox(check)


def test_antiskills_are_never_hot():
    def check(home):
        md = put_antiskill(home, "widget-trap")
        trust.record("widget-trap", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        entries = {e["name"]: e for e in read_json(home, "index.json")["entries"]}
        assert entries["widget-trap"]["tier"] == "warm"
        assert not native_md(home, "widget-trap").exists()
    in_sandbox(check)


def test_antiskills_do_not_consume_hot_budget():
    def check(home):
        # "aaa-trap" sorts BEFORE "zeta" once both are eligible and tied.
        md = put_antiskill(home, "aaa-trap")
        trust.record("aaa-trap", md.read_text(encoding="utf-8"), "self")
        md2 = put_skill(home, "zeta")
        trust.record("zeta", md2.read_text(encoding="utf-8"), "self")
        # Both earn eligibility, and identical timestamps make the tiebreak
        # name ASC -- so "aaa-trap" would take the only slot if anti-skills
        # still competed. That ordering is what gives this test its force.
        stamp = "2026-01-01T00:00:00+00:00"
        earn_success("aaa-trap", session="s1", ts=stamp)
        earn_success("zeta", session="s1", ts=stamp)
        os.environ["SKILLFORGE_HOT_BUDGET"] = "8"   # room for exactly one description
        try:
            sync.sync()
        finally:
            del os.environ["SKILLFORGE_HOT_BUDGET"]
        entries = {e["name"]: e for e in read_json(home, "index.json")["entries"]}
        assert entries["zeta"]["tier"] == "hot"     # the antiskill did not eat the budget
        assert entries["aaa-trap"]["tier"] == "warm"
    in_sandbox(check)


SKILL_WITH_SYMPTOMS = """---
name: %s
kind: skill
description: A thing. Do NOT use otherwise.
verification.command: "npx stripe trigger payment_intent.succeeded"
symptoms:
  - "SomeError: this should never fire from a plain skill"
---
## Procedure
1. Do it.
## Verification
Run the command.
"""


def test_skill_kind_symptoms_excluded_from_triggers():
    def check(home):
        # save_skill.validate never forbids `symptoms:` on kind: skill -- only
        # a kind: antiskill entry should compile into triggers.json's symptom
        # list, framed and budgeted as an anti-skill by detect.py.
        md = put_skill(home, "stripe-hook", SKILL_WITH_SYMPTOMS % "stripe-hook")
        trust.record("stripe-hook", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        trig = read_json(home, "triggers.json")
        assert trig["symptoms"] == []
        assert [v["skill"] for v in trig["verifications"]] == ["stripe-hook"]
    in_sandbox(check)


def test_antiskill_symptom_entries_carry_fingerprints():
    def check(home):
        md = put_antiskill(home, "widget-trap")
        trust.record("widget-trap", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        trig = read_json(home, "triggers.json")
        assert trig["symptoms"][0]["fingerprints"] == [
            ["await", "widget", "flush", "force", "true"]]
    in_sandbox(check)


SKILL_SINGLE_TOKEN = """---
name: %s
kind: skill
description: A thing. Do NOT use otherwise.
verification.command: "pytest"
fingerprints:
  - "make"
  - "express.raw({type: 'application/json'})"
---
## Procedure
1. Do it.
## Verification
Run the command.
"""


def test_single_token_verification_and_fingerprint_patterns_dropped():
    def check(home):
        # A verification.command or fingerprint that tokenizes to one common
        # word ("pytest", "make") would match nearly every unrelated Bash
        # call or file, inflating skill_aggregates.uses.
        md = put_skill(home, "single-tok", SKILL_SINGLE_TOKEN % "single-tok")
        trust.record("single-tok", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        trig = read_json(home, "triggers.json")
        assert trig["verifications"] == []   # "pytest" tokenizes to 1 token
        entries = {e["name"]: e for e in read_json(home, "index.json")["entries"]}
        assert entries["single-tok"]["fingerprints"] == [
            ["express", "raw", "type", "application", "json"]]  # "make" dropped
    in_sandbox(check)


def test_index_carries_tokenized_fingerprints():
    def check(home):
        md = put_skill(home, "stripe-hook", SKILL_WITH_TRIGGERS % "stripe-hook")
        trust.record("stripe-hook", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        entries = {e["name"]: e for e in read_json(home, "index.json")["entries"]}
        assert entries["stripe-hook"]["fingerprints"] == [
            ["express", "raw", "type", "application", "json"]]
    in_sandbox(check)


def earn_success(name, session="s1", ts=None):
    """Give a skill one successful session, the bar for `working`."""
    import ledger
    ledger.log_event("detection", name, detection="verification",
                     outcome="success", session=session, ts=ts)


def test_index_entries_carry_a_bucket():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["bucket"] == "unproven"
        earn_success("alpha")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["bucket"] == "working"
    in_sandbox(check)


def test_unproven_skill_never_goes_hot():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        counts = sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["tier"] == "warm"
        assert counts["materialized"] == 0
        assert not native_md(home, "alpha").exists()
    in_sandbox(check)


def test_working_skill_goes_hot():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["tier"] == "hot"
        assert native_md(home, "alpha").exists()
    in_sandbox(check)


def test_trusted_outranks_working_for_a_scarce_hot_slot():
    def check(home):
        for name in ("alpha", "beta"):
            md = put_skill(home, name)
            trust.record(name, md.read_text(encoding="utf-8"), "self")
        earn_success("alpha", session="s1")          # working
        earn_success("beta", session="s1")           # trusted: two sessions
        earn_success("beta", session="s2")

        def run():
            sync.sync()
            tiers = {e["name"]: e["tier"] for e in read_index(home)["entries"]}
            assert tiers == {"beta": "hot", "alpha": "warm"}, tiers
        with_budget("10", run)
    in_sandbox(check)


def signal_count():
    con = ledger.connect()
    try:
        return con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    finally:
        con.close()


def test_sync_sweeps_breadcrumbs_past_the_ttl():
    def check(home):
        stale = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(hours=sync.SIGNAL_TTL_HOURS + 1)
                 ).isoformat(timespec="seconds")
        ledger.log_signal("dead-session", "make test", False, ts=stale)
        sync.sync()
        assert signal_count() == 0
    in_sandbox(check)


def test_sync_keeps_fresh_breadcrumbs():
    def check(home):
        ledger.log_signal("live-session", "make test", False)
        sync.sync()
        assert signal_count() == 1
    in_sandbox(check)


def test_index_and_triggers_go_through_an_atomic_rename():
    """A reader must never see a half-written index.

    Both files are rewritten wholesale on every sync while hooks read them
    on every tool call and prompt. A bare write_text truncates first and
    fills second; a crash in that gap leaves a truncated file, which both
    readers treat as "no index" -- silently disabling injection until the
    next successful sync.
    """
    def check(home):
        seen = []
        real = os.replace

        def spy(src, dst):
            seen.append((src, dst))
            return real(src, dst)

        os.replace = spy
        try:
            sync._write_index([])
            sync._write_triggers([])
        finally:
            os.replace = real

        d = home / ".claude" / "skillforge"
        assert len(seen) == 2, "writes did not go through os.replace: %r" % (seen,)
        for src, dst in seen:
            # Same directory, or the rename is not atomic on POSIX.
            assert os.path.dirname(src) == os.path.dirname(dst), (src, dst)
        assert not list(d.glob("*.tmp-*")), sorted(x.name for x in d.iterdir())
        assert json.loads((d / "index.json").read_text())["entries"] == []
        assert json.loads((d / "triggers.json").read_text())["symptoms"] == []
    in_sandbox(check)


def test_an_interrupted_write_leaves_the_previous_index_intact():
    """The point of temp-then-rename: an interrupted write is a no-op.

    Injects a partial write -- content lands, then the write fails -- which
    is what a full disk or a kill mid-write actually looks like. Writing
    straight to the destination corrupts it; writing to a temp does not,
    because os.replace never runs.
    """
    def check(home):
        sync._write_index([])
        p = home / ".claude" / "skillforge" / "index.json"
        before = p.read_text()
        assert json.loads(before)["entries"] == []

        real = pathlib.Path.write_text

        def partial(self, data, *a, **k):
            real(self, data[:len(data) // 2], *a, **k)   # truncated on disk
            raise OSError(28, "No space left on device")

        pathlib.Path.write_text = partial
        try:
            try:
                sync._write_index([])
            except OSError:
                pass
        finally:
            pathlib.Path.write_text = real

        assert p.read_text() == before, "the previous index was corrupted"
        assert json.loads(p.read_text())["entries"] == []
        # And it leaves no orphan behind: nothing sweeps this directory, so a
        # temp stranded by a failed write would persist forever.
        assert not list(p.parent.glob("*.tmp-*")), \
            sorted(x.name for x in p.parent.iterdir())
    in_sandbox(check)


SKILL_WITH_PROVENANCE = """---
name: %s
kind: skill
description: A thing. Do NOT use otherwise.
verification.command: "npx stripe trigger payment_intent.succeeded"
provenance:
  repo: /tmp/acme-storefront
  distilled: 2026-08-01
---
## Procedure
1. Do it.
## Verification
Run the command.
"""


def test_sync_applies_the_tier_a_conjunct_to_tiering():
    """Two clean sessions alone are `working`; `trusted` needs a critique pass.

    (Adapted from the brief: put_skill() writes a store file, it does not
    trust it, so trust.record() is added the way every other test here does
    it. The brief's `tier == "warm"` assertion is replaced by `hot`: working
    is hot-eligible -- test_working_skill_goes_hot has always asserted that
    -- so the conjunct's effect is on the bucket, which is asserted.)
    """
    def check(home):
        path = put_skill(home, "widget-flush")
        text = pathlib.Path(path).read_text(encoding="utf-8")
        trust.record("widget-flush", text, "self")
        for i in range(2):
            ledger.log_event("detection", "widget-flush", outcome="success",
                             session="s%d" % i)
        sync.sync()
        entry = [e for e in read_index(home)["entries"]
                 if e["name"] == "widget-flush"][0]
        assert entry["bucket"] == "working", entry
        assert entry["tier"] == "hot", entry

        ledger.record_validation("widget-flush", trust.content_hash(text),
                                 "critique", "pass")
        sync.sync()
        entry = [e for e in read_index(home)["entries"]
                 if e["name"] == "widget-flush"][0]
        assert entry["bucket"] == "trusted", entry
    in_sandbox(check)


def test_executable_candidates_are_ordered_by_evidence_then_recency():
    conf = {"a": {"successes": 0}, "b": {"successes": 3}, "c": {"successes": 1}}
    trusted = [{"name": n, "saved_ts": t} for n, t in
               (("a", "2026-01-03"), ("b", "2026-01-01"), ("c", "2026-01-02"))]
    verdicts = {n: {"critique": "pass"} for n in "abc"}
    got = sync.executable_candidates(trusted, conf, verdicts)
    assert got == ["b", "c", "a"], got


def test_executable_candidates_break_ties_by_recency():
    """Equal evidence: only the saved_ts comparator can order these, and it
    must reverse the input order to prove it ran at all."""
    conf = {"a": {"successes": 2}, "b": {"successes": 2}}
    trusted = [{"name": "a", "saved_ts": 100.0}, {"name": "b", "saved_ts": 200.0}]
    verdicts = {n: {"critique": "pass"} for n in "ab"}
    got = sync.executable_candidates(trusted, conf, verdicts)
    assert got == ["b", "a"], got


def test_a_skill_without_critique_is_not_an_executable_candidate():
    conf = {"a": {"successes": 5}}
    trusted = [{"name": "a", "saved_ts": "2026-01-01"}]
    assert sync.executable_candidates(trusted, conf, {}) == []
    assert sync.executable_candidates(
        trusted, conf, {"a": {"critique": "fail"}}) == []


def test_a_skill_already_executable_validated_is_not_a_candidate():
    conf = {"a": {"successes": 5}}
    trusted = [{"name": "a", "saved_ts": "2026-01-01"}]
    for verdict in ("pass", "fail", "inconclusive"):
        assert sync.executable_candidates(
            trusted, conf,
            {"a": {"critique": "pass", "executable": verdict}}) == [], verdict


def test_an_antiskill_is_not_an_executable_candidate():
    """Anti-skills carry no verification.command by design, so executable
    mode can only ever answer `inconclusive` -- which is no longer recorded,
    so an anti-skill candidate would burn the one slot every session."""
    conf = {"a": {"successes": 5}}
    trusted = [{"name": "a", "saved_ts": 1.0, "kind": "antiskill",
                "verification_command": "npx stripe trigger x"}]
    verdicts = {"a": {"critique": "pass"}}
    assert sync.executable_candidates(trusted, conf, verdicts) == []
    trusted[0]["kind"] = "skill"        # identical otherwise: `kind` excluded it
    assert sync.executable_candidates(trusted, conf, verdicts) == ["a"]


def test_a_skill_without_a_verification_command_is_not_a_candidate():
    conf = {"a": {"successes": 5}}
    trusted = [{"name": "a", "saved_ts": 1.0, "kind": "skill",
                "verification_command": ""}]
    verdicts = {"a": {"critique": "pass"}}
    assert sync.executable_candidates(trusted, conf, verdicts) == []
    trusted[0]["verification_command"] = "npx stripe trigger x"
    assert sync.executable_candidates(trusted, conf, verdicts) == ["a"]


def test_sync_spawns_at_most_one_executable_run():
    def check(home):
        seen = []
        real = sync._spawn_validation
        sync._spawn_validation = lambda name, mode: seen.append((name, mode))
        try:
            for n in ("aaa-skill", "bbb-skill"):
                p = put_skill(home, n, SKILL_WITH_TRIGGERS % n)
                text = pathlib.Path(p).read_text(encoding="utf-8")
                trust.record(n, text, "self")
                ledger.record_validation(
                    n, trust.content_hash(text), "critique", "pass")
            sync.sync()
        finally:
            sync._spawn_validation = real
        assert len(seen) == 1, seen
        assert seen[0][1] == "executable", seen
    in_sandbox(check)


def test_index_entries_carry_provenance():
    """validate.executable() reads entry["provenance"]["repo"] to know which
    repo to reproduce; without this carry it is `inconclusive` every time."""
    def check(home):
        md = put_skill(home, "stripe-hook", SKILL_WITH_PROVENANCE % "stripe-hook")
        trust.record("stripe-hook", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["provenance"] == {"repo": "/tmp/acme-storefront",
                                       "distilled": "2026-08-01"}, entry
    in_sandbox(check)


def test_a_non_mapping_provenance_does_not_raise():
    def check(home):
        text = (SKILL_WITH_PROVENANCE % "stripe-hook").replace(
            "provenance:\n  repo: /tmp/acme-storefront\n  distilled: 2026-08-01",
            "provenance: garbage")
        md = put_skill(home, "stripe-hook", text)
        trust.record("stripe-hook", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["provenance"] == {}, entry
    in_sandbox(check)


def _capture_popen_env(name="widget-flush", mode="executable"):
    """Call the REAL _spawn_validation with subprocess.Popen stubbed out.

    Never spawns a real process -- Popen itself is replaced -- but still
    exercises the actual env-construction logic in sync.py, which the
    seam-swap test above never touches (it replaces _spawn_validation
    wholesale). Returns the `env` kwarg the real function handed to Popen.
    """
    calls = []
    real_popen = sync.subprocess.Popen

    class DummyProc:
        pass

    def fake_popen(argv, **kwargs):
        calls.append(kwargs.get("env"))
        return DummyProc()

    sync.subprocess.Popen = fake_popen
    try:
        _REAL_SPAWN_VALIDATION(name, mode)
    finally:
        sync.subprocess.Popen = real_popen
    return calls[0]


def test_spawn_does_not_manufacture_the_drafting_flag():
    """validate.py's main() returns 0 as its first statement when the flag is
    set, so forcing it here would make every scheduled run a silent no-op."""
    old = os.environ.pop("SKILLFORGE_DRAFTING", None)
    try:
        env = _capture_popen_env()
        assert "SKILLFORGE_DRAFTING" not in env, env
    finally:
        if old is not None:
            os.environ["SKILLFORGE_DRAFTING"] = old


def test_spawn_inherits_the_drafting_flag_when_already_set():
    old = os.environ.get("SKILLFORGE_DRAFTING")
    os.environ["SKILLFORGE_DRAFTING"] = "1"
    try:
        env = _capture_popen_env()
        assert env.get("SKILLFORGE_DRAFTING") == "1", env
    finally:
        if old is None:
            del os.environ["SKILLFORGE_DRAFTING"]
        else:
            os.environ["SKILLFORGE_DRAFTING"] = old


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
