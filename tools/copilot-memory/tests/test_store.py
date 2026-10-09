"""Tests for the store module — file I/O with validation."""

import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from copilot_memory.models import Rule, RulesFile, ContextFile, SessionEntry, LatestSession
from copilot_memory.store import (
    _read_yaml,
    _write_yaml,
    _read_json,
    _write_json,
    load_rules,
    save_rules,
    load_context,
    save_context,
    load_prefs,
    save_prefs,
    load_latest_session,
    save_latest_session,
    load_session,
    check_session_integrity,
    make_project_slug,
)


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal project memory structure."""
    (tmp_path / "sessions" / "_default").mkdir(parents=True)
    return tmp_path


class TestYamlIO:
    def test_read_missing_file(self, tmp_path):
        assert _read_yaml(tmp_path / "nope.yml") == {}

    def test_read_empty_file(self, tmp_path):
        (tmp_path / "empty.yml").write_text("", encoding="utf-8")
        assert _read_yaml(tmp_path / "empty.yml") == {}

    def test_write_adds_schema_version(self, tmp_path):
        fpath = tmp_path / "test.yml"
        _write_yaml(fpath, {"key": "value"})
        data = yaml.safe_load(fpath.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
        assert data["key"] == "value"

    def test_write_preserves_existing_schema_version(self, tmp_path):
        fpath = tmp_path / "test.yml"
        _write_yaml(fpath, {"schema_version": 2, "key": "value"})
        data = yaml.safe_load(fpath.read_text(encoding="utf-8"))
        assert data["schema_version"] == 2

    def test_write_creates_parent_dirs(self, tmp_path):
        fpath = tmp_path / "deep" / "nested" / "test.yml"
        _write_yaml(fpath, {"x": 1})
        assert fpath.exists()

    def test_atomic_write_no_partial(self, tmp_path):
        """Temp file should not persist after successful write."""
        fpath = tmp_path / "test.yml"
        _write_yaml(fpath, {"x": 1})
        assert not (tmp_path / "test.tmp").exists()


class TestJsonIO:
    def test_read_missing(self, tmp_path):
        assert _read_json(tmp_path / "nope.json") == {}

    def test_roundtrip(self, tmp_path):
        fpath = tmp_path / "test.json"
        _write_json(fpath, {"key": "value", "num": 42})
        data = _read_json(fpath)
        assert data["key"] == "value"
        assert data["num"] == 42


class TestRulesOperations:
    def test_load_empty(self, tmp_project):
        rules = load_rules(tmp_project)
        assert rules.rules == []
        assert rules.schema_version == 1

    def test_save_and_load(self, tmp_project):
        rf = RulesFile(rules=[
            Rule(id="use-ts", type="do", description="Use TypeScript"),
            Rule(id="no-any", type="dont", description="Never use any"),
        ])
        save_rules(tmp_project, rf)
        loaded = load_rules(tmp_project)
        assert len(loaded.rules) == 2
        assert loaded.rules[0].id == "use-ts"
        assert loaded.rules[1].type == "dont"

    def test_load_skips_malformed_rules(self, tmp_project):
        """Rules with missing/invalid fields should be skipped, not crash."""
        _write_yaml(tmp_project / "rules.yml", {
            "schema_version": 1,
            "rules": [
                {"id": "good-rule", "type": "do", "description": "Valid"},
                {"type": "do", "description": "Missing ID"},  # no id
                {"id": "Bad ID!", "type": "do", "description": "Invalid ID"},
                {"id": "good-two", "type": "do", "description": "Also valid"},
            ],
        })
        rules = load_rules(tmp_project)
        assert len(rules.rules) == 2
        assert rules.rules[0].id == "good-rule"
        assert rules.rules[1].id == "good-two"

    def test_saved_file_has_schema_version(self, tmp_project):
        save_rules(tmp_project, RulesFile())
        data = yaml.safe_load(
            (tmp_project / "rules.yml").read_text(encoding="utf-8")
        )
        assert data["schema_version"] == 1


class TestContextOperations:
    def test_load_empty(self, tmp_project):
        ctx = load_context(tmp_project)
        assert ctx.name == ""
        assert ctx.stack == []

    def test_save_and_load(self, tmp_project):
        ctx = ContextFile(name="TestProject", stack=["Python", "FastAPI"])
        save_context(tmp_project, ctx)
        loaded = load_context(tmp_project)
        assert loaded.name == "TestProject"
        assert loaded.stack == ["Python", "FastAPI"]


class TestPrefsOperations:
    def test_load_empty(self, tmp_project):
        prefs = load_prefs(tmp_project)
        assert prefs["schema_version"] == 1

    def test_save_and_load(self, tmp_project):
        save_prefs(tmp_project, {
            "language": "typescript",
            "indent": 2,
        })
        loaded = load_prefs(tmp_project)
        assert loaded["language"] == "typescript"
        assert loaded["indent"] == 2
        assert loaded["schema_version"] == 1  # auto-added


class TestSessionOperations:
    def test_load_latest_empty(self, tmp_project):
        assert load_latest_session(tmp_project) is None

    def test_save_and_load_latest(self, tmp_project):
        latest = LatestSession(lastSessionId="abc-123", lastUpdatedAt="2026-06-11")
        save_latest_session(tmp_project, latest)
        loaded = load_latest_session(tmp_project)
        assert loaded is not None
        assert loaded.lastSessionId == "abc-123"

    def test_load_session_file(self, tmp_project):
        session_data = {
            "sessionId": "test-session-1",
            "status": "active",
            "startedAt": "2026-06-11T10:00:00Z",
            "lastUpdatedAt": "2026-06-11T10:30:00Z",
            "summary": "Test session",
        }
        fpath = tmp_project / "sessions" / "_default" / "test-session-1.json"
        fpath.write_text(json.dumps(session_data), encoding="utf-8")

        entry = load_session(fpath)
        assert entry is not None
        assert entry.sessionId == "test-session-1"
        assert entry.status == "active"


class TestSessionIntegrity:
    def test_detects_dangling_pointer(self, tmp_project):
        _write_json(tmp_project / "sessions" / "latest.json", {
            "lastSessionId": "nonexistent-id",
            "lastUpdatedAt": "2026-06-11",
        })
        dangling, mismatched = check_session_integrity(tmp_project)
        assert len(dangling) == 1
        assert "nonexistent-id" in dangling[0]

    def test_detects_id_mismatch(self, tmp_project):
        fpath = tmp_project / "sessions" / "_default" / "file-name-id.json"
        fpath.write_text(json.dumps({
            "sessionId": "different-id",
            "status": "active",
        }), encoding="utf-8")

        dangling, mismatched = check_session_integrity(tmp_project)
        assert len(mismatched) == 1
        assert "file-name-id" in mismatched[0]
        assert "different-id" in mismatched[0]

    def test_clean_state_no_issues(self, tmp_project):
        # Create a valid session
        sid = "valid-session-1"
        fpath = tmp_project / "sessions" / "_default" / f"{sid}.json"
        fpath.write_text(json.dumps({
            "sessionId": sid,
            "status": "active",
        }), encoding="utf-8")
        _write_json(tmp_project / "sessions" / "latest.json", {
            "lastSessionId": sid,
            "lastUpdatedAt": "2026-06-11",
        })

        dangling, mismatched = check_session_integrity(tmp_project)
        assert len(dangling) == 0
        assert len(mismatched) == 0


class TestProjectSlug:
    def test_basic_slug(self):
        slug = make_project_slug("/home/user/my-project")
        assert slug.startswith("my-project-")
        assert len(slug.split("-")[-1]) == 8  # hash suffix

    def test_underscores_converted(self):
        slug = make_project_slug("/repo/AI_BlackBox")
        assert slug.startswith("ai-blackbox-")

    def test_deterministic(self):
        slug1 = make_project_slug("/repo/test")
        slug2 = make_project_slug("/repo/test")
        assert slug1 == slug2

    def test_different_paths_different_hashes(self):
        slug1 = make_project_slug("/repo/project-a")
        slug2 = make_project_slug("/repo/project-b")
        assert slug1 != slug2


class TestSessionCompactionThreshold:
    def _mk(self, **kwargs):
        base = dict(
            sessionId="s1",
            status="active",
            startedAt="2026-06-11T00:00:00Z",
            lastUpdatedAt="2026-06-11T00:00:00Z",
        )
        base.update(kwargs)
        return SessionEntry(**base)

    def test_empty_session_within_limits(self):
        from copilot_memory.store import session_needs_compaction

        needs, reasons = session_needs_compaction(self._mk())
        assert not needs
        assert reasons == []

    def test_entries_threshold_trips(self):
        from copilot_memory.store import session_needs_compaction

        entry = self._mk(
            decisions=[f"d{i}" for i in range(15)],
            learnings=[f"l{i}" for i in range(10)],
        )
        needs, reasons = session_needs_compaction(entry)
        assert needs
        assert any("decisions+learnings" in r for r in reasons)

    def test_files_threshold_trips(self):
        from copilot_memory.store import session_needs_compaction

        entry = self._mk(filesChanged=[f"src/f{i}.py" for i in range(31)])
        needs, reasons = session_needs_compaction(entry)
        assert needs
        assert any("filesChanged" in r for r in reasons)

    def test_size_threshold_trips(self):
        from copilot_memory.store import session_needs_compaction

        entry = self._mk(summary="x" * (9 * 1024))
        needs, reasons = session_needs_compaction(entry)
        assert needs
        assert any("size=" in r for r in reasons)

    def test_boundary_20_entries_still_ok(self):
        from copilot_memory.store import session_needs_compaction

        entry = self._mk(
            decisions=[f"d{i}" for i in range(10)],
            learnings=[f"l{i}" for i in range(10)],
        )
        needs, reasons = session_needs_compaction(entry)
        assert not needs

    def test_defaults_for_new_fields(self):
        entry = self._mk()
        assert entry.compactedSummary == ""
        assert entry.compactionCount == 0

    def test_new_fields_roundtrip(self):
        entry = self._mk(compactedSummary="prose", compactionCount=3)
        dumped = entry.model_dump()
        assert dumped["compactedSummary"] == "prose"
        assert dumped["compactionCount"] == 3


class TestSessionArchival:
    def _mk_session_file(self, sessions_dir, sid, status, ended_at,
                        started_at="2026-01-01T00:00:00Z"):
        path = sessions_dir / f"{sid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "sessionId": sid,
            "status": status,
            "startedAt": started_at,
            "lastUpdatedAt": ended_at,
            "endedAt": ended_at if status == "closed" else None,
            "summary": "x" * 500,
        }), encoding="utf-8")
        return path

    def test_archives_old_closed_sessions(self, tmp_project):
        from datetime import datetime, timezone
        from copilot_memory.store import archive_closed_sessions, load_session

        sd = tmp_project / "sessions" / "_default"
        old_path = self._mk_session_file(sd, "old-closed", "closed",
                                         "2020-01-01T00:00:00Z")

        now = datetime(2026, 6, 11, tzinfo=timezone.utc)
        archived = archive_closed_sessions(tmp_project, older_than_days=7, now=now)

        assert len(archived) == 1
        assert not old_path.exists()
        gz = old_path.with_suffix(".json.gz")
        assert gz.exists()
        # Transparent read still works
        entry = load_session(gz)
        assert entry is not None
        assert entry.sessionId == "old-closed"

    def test_skips_active_sessions(self, tmp_project):
        from datetime import datetime, timezone
        from copilot_memory.store import archive_closed_sessions

        sd = tmp_project / "sessions" / "_default"
        p = self._mk_session_file(sd, "active-one", "active",
                                  "2020-01-01T00:00:00Z")
        now = datetime(2026, 6, 11, tzinfo=timezone.utc)
        archived = archive_closed_sessions(tmp_project, older_than_days=7, now=now)
        assert archived == []
        assert p.exists()

    def test_skips_recent_closed_sessions(self, tmp_project):
        from datetime import datetime, timezone
        from copilot_memory.store import archive_closed_sessions

        sd = tmp_project / "sessions" / "_default"
        p = self._mk_session_file(sd, "recent-closed", "closed",
                                  "2026-06-10T00:00:00Z")
        now = datetime(2026, 6, 11, tzinfo=timezone.utc)
        archived = archive_closed_sessions(tmp_project, older_than_days=7, now=now)
        assert archived == []
        assert p.exists()

    def test_transparent_fallback_when_only_gz_exists(self, tmp_project):
        from copilot_memory.store import _read_json
        import gzip as _gz

        sd = tmp_project / "sessions" / "_default"
        gz = sd / "only.json.gz"
        gz.parent.mkdir(parents=True, exist_ok=True)
        gz.write_bytes(_gz.compress(json.dumps({"sessionId": "only"}).encode()))
        # Requesting the .json path should transparently read the .gz sibling
        data = _read_json(sd / "only.json")
        assert data == {"sessionId": "only"}

    def test_find_session_file_finds_gz(self, tmp_project):
        from datetime import datetime, timezone
        from copilot_memory.store import archive_closed_sessions, find_session_file

        sd = tmp_project / "sessions" / "_default"
        self._mk_session_file(sd, "old-closed", "closed", "2020-01-01T00:00:00Z")
        archive_closed_sessions(tmp_project, older_than_days=7,
                                 now=datetime(2026, 6, 11, tzinfo=timezone.utc))
        found = find_session_file(tmp_project, "old-closed")
        assert found is not None
        assert found.name.endswith(".json.gz")

    def test_list_sessions_includes_gz(self, tmp_project):
        from datetime import datetime, timezone
        from copilot_memory.store import archive_closed_sessions, list_sessions

        sd = tmp_project / "sessions" / "_default"
        self._mk_session_file(sd, "old-closed", "closed", "2020-01-01T00:00:00Z")
        self._mk_session_file(sd, "active-one", "active", "2026-06-10T00:00:00Z")
        archive_closed_sessions(tmp_project, older_than_days=7,
                                 now=datetime(2026, 6, 11, tzinfo=timezone.utc))
        entries = list_sessions(tmp_project)
        ids = {e.sessionId for _, e in entries}
        assert ids == {"old-closed", "active-one"}


class TestSessionMerge:
    def _mk(self, sid, **kwargs):
        base = dict(
            sessionId=sid,
            status="active",
            startedAt="2026-06-01T00:00:00Z",
            lastUpdatedAt="2026-06-01T00:00:00Z",
        )
        base.update(kwargs)
        return SessionEntry(**base)

    def _write(self, project_dir, entry):
        from copilot_memory.store import _write_json
        p = project_dir / "sessions" / "_default" / f"{entry.sessionId}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        _write_json(p, entry.model_dump())
        return p

    def test_merge_two_sessions_unions_and_dedupes(self, tmp_project):
        from copilot_memory.store import merge_sessions, load_session

        a = self._mk("sess-a",
                     filesChanged=["a.py", "shared.py"],
                     decisions=["chose SQLite"],
                     learnings=["needs indexing"])
        b = self._mk("sess-b",
                     filesChanged=["b.py", "shared.py"],
                     decisions=["chose FastAPI"],
                     learnings=["needs indexing", "uvicorn under gunicorn"])
        self._write(tmp_project, a)
        self._write(tmp_project, b)

        merged, path = merge_sessions(
            tmp_project,
            parent_ids=["sess-a", "sess-b"],
            new_session_id="merged-1",
            now_iso_str="2026-06-11T00:00:00Z",
        )
        assert path.exists()
        assert merged.parents == ["sess-a", "sess-b"]
        # union + dedupe
        assert merged.filesChanged == ["a.py", "shared.py", "b.py"]
        assert set(merged.decisions) == {"chose SQLite", "chose FastAPI"}
        assert set(merged.learnings) == {"needs indexing", "uvicorn under gunicorn"}
        # persisted file matches
        reloaded = load_session(path)
        assert reloaded.parents == ["sess-a", "sess-b"]
        assert reloaded.compactedSummary  # digest was written

    def test_merge_pushes_overflow_into_compacted_summary(self, tmp_project):
        from copilot_memory.store import merge_sessions

        a = self._mk("sess-a",
                     decisions=[f"d{i}" for i in range(15)],
                     learnings=[f"l{i}" for i in range(15)])
        self._write(tmp_project, a)
        merged, _ = merge_sessions(
            tmp_project,
            parent_ids=["sess-a"],
            new_session_id="merged-1",
            now_iso_str="2026-06-11T00:00:00Z",
        )
        # Overflow: only last 5 of each kept verbatim
        assert merged.decisions == [f"d{i}" for i in range(10, 15)]
        assert merged.learnings == [f"l{i}" for i in range(10, 15)]
        assert merged.compactionCount >= 1
        assert "older decisions dropped" in merged.compactedSummary

    def test_merge_missing_parent_raises(self, tmp_project):
        from copilot_memory.store import merge_sessions

        self._write(tmp_project, self._mk("real"))
        with pytest.raises(ValueError, match="Unknown session"):
            merge_sessions(
                tmp_project,
                parent_ids=["real", "ghost"],
                new_session_id="x",
                now_iso_str="2026-06-11T00:00:00Z",
            )

    def test_merge_dry_run_does_not_write(self, tmp_project):
        from copilot_memory.store import merge_sessions

        self._write(tmp_project, self._mk("sess-a", filesChanged=["a.py"]))
        merged, path = merge_sessions(
            tmp_project,
            parent_ids=["sess-a"],
            new_session_id="preview-1",
            now_iso_str="2026-06-11T00:00:00Z",
            dry_run=True,
        )
        assert path is None
        assert merged.parents == ["sess-a"]
        # Nothing new on disk
        default_dir = tmp_project / "sessions" / "_default"
        assert not (default_dir / "preview-1.json").exists()

    def test_merge_into_named_folder_updates_latest(self, tmp_project):
        from copilot_memory.store import merge_sessions, load_latest_session

        self._write(tmp_project, self._mk("sess-a"))
        merged, path = merge_sessions(
            tmp_project,
            parent_ids=["sess-a"],
            new_session_id="feature-x-1",
            now_iso_str="2026-06-11T00:00:00Z",
            into_name="feature-x",
        )
        assert "feature-x" in str(path)
        latest = load_latest_session(tmp_project)
        assert latest.lastSessionId == "feature-x-1"
        assert latest.activeSession == "feature-x"


class TestSessionStack:
    def _mk(self, sid, **kwargs):
        base = dict(
            sessionId=sid,
            status="active",
            startedAt="2026-06-01T00:00:00Z",
            lastUpdatedAt="2026-06-01T00:00:00Z",
        )
        base.update(kwargs)
        return SessionEntry(**base)

    def _write(self, project_dir, entry):
        p = project_dir / "sessions" / "_default" / f"{entry.sessionId}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        _write_json(p, entry.model_dump())
        return p

    def test_upsert_and_load_stack(self, tmp_project):
        from copilot_memory.store import upsert_stack, load_stacks, find_stack

        upsert_stack(tmp_project, "common", ["a", "b"], "2026-06-11T00:00:00Z",
                     description="everyday")
        stacks = load_stacks(tmp_project)
        s = find_stack(stacks, "common")
        assert s is not None
        assert s.sessions == ["a", "b"]
        assert s.description == "everyday"

    def test_upsert_replace_and_append(self, tmp_project):
        from copilot_memory.store import upsert_stack, load_stacks, find_stack

        upsert_stack(tmp_project, "bms", ["a", "b"], "t")
        upsert_stack(tmp_project, "bms", ["b", "c"], "t", append=True)
        s = find_stack(load_stacks(tmp_project), "bms")
        assert s.sessions == ["a", "b", "c"]  # deduped append
        upsert_stack(tmp_project, "bms", ["x"], "t")  # replace
        s = find_stack(load_stacks(tmp_project), "bms")
        assert s.sessions == ["x"]

    def test_remove_from_stack_and_delete(self, tmp_project):
        from copilot_memory.store import upsert_stack, remove_from_stack, load_stacks, find_stack

        upsert_stack(tmp_project, "s", ["a", "b", "c"], "t")
        remove_from_stack(tmp_project, "s", ["b"], "t")
        assert find_stack(load_stacks(tmp_project), "s").sessions == ["a", "c"]
        deleted = remove_from_stack(tmp_project, "s", None, "t")
        assert deleted is None
        assert find_stack(load_stacks(tmp_project), "s") is None

    def test_remove_unknown_stack_raises(self, tmp_project):
        from copilot_memory.store import remove_from_stack

        with pytest.raises(KeyError):
            remove_from_stack(tmp_project, "ghost", None, "t")

    def test_assemble_stack_top_wins_and_dedupes(self, tmp_project):
        from copilot_memory.store import assemble_stack

        self._write(tmp_project, self._mk(
            "base", decisions=["use SQLite"], learnings=["index it"],
            filesChanged=["a.py", "shared.py"]))
        self._write(tmp_project, self._mk(
            "top", decisions=["use Postgres"], learnings=["index it", "pool conns"],
            filesChanged=["b.py", "shared.py"]))
        rendered, structured = assemble_stack(tmp_project, ["base", "top"])
        assert structured["layers"] == ["base", "top"]
        # dedupe preserved, both decisions present
        assert "use SQLite" in structured["decisions"]
        assert "use Postgres" in structured["decisions"]
        assert structured["learnings"].count("index it") == 1
        assert "shared.py" in structured["filesChanged"]
        assert structured["filesChanged"].count("shared.py") == 1
        assert "Layered context" in rendered

    def test_assemble_stack_missing_raises(self, tmp_project):
        from copilot_memory.store import assemble_stack

        self._write(tmp_project, self._mk("real"))
        with pytest.raises(ValueError, match="Unknown session"):
            assemble_stack(tmp_project, ["real", "ghost"])

    def test_nested_stack_reference_resolves(self, tmp_project):
        from copilot_memory.store import upsert_stack, assemble_stack

        self._write(tmp_project, self._mk("a", decisions=["A"]))
        self._write(tmp_project, self._mk("b", decisions=["B"]))
        self._write(tmp_project, self._mk("c", decisions=["C"]))
        upsert_stack(tmp_project, "inner", ["a", "b"], "t")
        # outer references the inner stack via @inner, then adds c on top
        _, structured = assemble_stack(tmp_project, ["@inner", "c"])
        assert structured["layers"] == ["a", "b", "c"]
        assert structured["decisions"] == ["A", "B", "C"]

    def test_cyclic_stack_reference_raises(self, tmp_project):
        from copilot_memory.store import upsert_stack, assemble_stack

        self._write(tmp_project, self._mk("a"))
        upsert_stack(tmp_project, "x", ["@y", "a"], "t")
        upsert_stack(tmp_project, "y", ["@x"], "t")
        with pytest.raises(ValueError, match="[Cc]yclic|too deep"):
            assemble_stack(tmp_project, ["@x"])

    def test_cross_repo_and_global_reference(self, tmp_path, monkeypatch):
        from copilot_memory import store as store_mod

        root = tmp_path / "memroot"
        (root / "_global").mkdir(parents=True)
        monkeypatch.setattr(store_mod, "MEMORY_ROOT", root)
        monkeypatch.setattr(store_mod, "GLOBAL_DIR", root / "_global")

        repo_a = root / "repo-a"
        repo_b = root / "repo-b"
        for r, sid, dec in ((repo_a, "auth", "A-auth"), (repo_b, "api", "B-api")):
            (r / "sessions" / "_default").mkdir(parents=True)
            _write_json(r / "sessions" / "_default" / f"{sid}.json",
                        self._mk(sid, decisions=[dec]).model_dump())

        # global stack references a session in each repo
        store_mod.upsert_stack(repo_a, "multi", ["repo-a/auth", "repo-b/api"], "t",
                               catalog_dir=root / "_global")
        # resolve from repo_a via @multi (found in global), layering base repo_a
        _, structured = store_mod.assemble_stack(repo_a, ["@multi"])
        assert structured["layers"] == ["auth", "repo-b/api"]
        assert set(structured["repos"]) == {"repo-a", "repo-b"}
        assert structured["decisions"] == ["A-auth", "B-api"]

    def test_show_previews_exactly_what_apply_persists(self, tmp_project):
        """show (assemble_stack) must preview the same content apply persists."""
        from copilot_memory.store import assemble_stack, apply_stack, load_session

        # Enough entries to cross the merge compaction threshold so the two
        # code paths would diverge if they used different engines.
        self._write(tmp_project, self._mk(
            "base",
            decisions=[f"d-base-{i}" for i in range(12)],
            learnings=[f"l-base-{i}" for i in range(12)],
            filesChanged=[f"base-{i}.py" for i in range(20)]))
        self._write(tmp_project, self._mk(
            "top",
            decisions=[f"d-top-{i}" for i in range(12)],
            learnings=[f"l-top-{i}" for i in range(12)],
            filesChanged=[f"top-{i}.py" for i in range(20)]))

        _, structured = assemble_stack(tmp_project, ["base", "top"])
        merged, path = apply_stack(
            tmp_project, ["base", "top"],
            new_session_id="applied-1", now_iso_str="2026-06-11T00:00:00Z")
        persisted = load_session(path)

        # The preview's merged fields equal what got written to disk.
        assert structured["decisions"] == persisted.decisions == merged.decisions
        assert structured["learnings"] == persisted.learnings == merged.learnings
        assert structured["filesChanged"] == persisted.filesChanged == merged.filesChanged
        assert structured["compactedSummary"] == persisted.compactedSummary

    def test_provenance_surfaces_conflicting_decisions(self, tmp_project):
        """Contradictory decisions from different layers must be traceable to
        their source layer, since exact-string dedupe keeps both."""
        from copilot_memory.store import assemble_stack

        self._write(tmp_project, self._mk("base", decisions=["use SQLite"]))
        self._write(tmp_project, self._mk("top", decisions=["use PostgreSQL"]))

        rendered, structured = assemble_stack(tmp_project, ["base", "top"])

        # Both survive (no semantic resolution) but each is attributed.
        prov = structured["provenance"]["decisions"]
        assert prov["use SQLite"] == ["base"]
        assert prov["use PostgreSQL"] == ["top"]
        # Rendered output tags each entry with its origin layer.
        assert "use SQLite  ⟵ base" in rendered
        assert "use PostgreSQL  ⟵ top" in rendered

    def test_provenance_records_agreement_across_layers(self, tmp_project):
        """A value present in multiple layers lists all contributing layers
        base→top (last = authoritative)."""
        from copilot_memory.store import assemble_stack

        self._write(tmp_project, self._mk("base", decisions=["always lint"]))
        self._write(tmp_project, self._mk("top", decisions=["always lint"]))

        _, structured = assemble_stack(tmp_project, ["base", "top"])
        assert structured["provenance"]["decisions"]["always lint"] == ["base", "top"]

    def test_single_layer_has_no_provenance_noise(self, tmp_project):
        """A one-layer stack should not clutter output with ⟵ tags."""
        from copilot_memory.store import assemble_stack

        self._write(tmp_project, self._mk("solo", decisions=["ship it"]))
        rendered, structured = assemble_stack(tmp_project, ["solo"])
        assert "⟵" not in rendered
        assert structured["provenance"]["decisions"]["ship it"] == ["solo"]

    def test_no_false_truncation_flag(self, tmp_project):
        """compactedSummary always carries lineage digests; the truncation flag
        must stay False when nothing actually exceeded the merge cap."""
        from copilot_memory.store import assemble_stack

        self._write(tmp_project, self._mk("base", decisions=["a"], learnings=["x"]))
        self._write(tmp_project, self._mk("top", decisions=["b"], learnings=["y"]))
        rendered, structured = assemble_stack(tmp_project, ["base", "top"])
        assert structured["truncated"] is False
        assert "fold into compactedSummary" not in rendered

    def test_truncation_flag_set_when_cap_exceeded(self, tmp_project):
        from copilot_memory.store import assemble_stack

        self._write(tmp_project, self._mk(
            "base", decisions=[f"d{i}" for i in range(15)],
            learnings=[f"l{i}" for i in range(15)]))
        rendered, structured = assemble_stack(tmp_project, ["base"])
        assert structured["truncated"] is True
        assert "fold into compactedSummary" in rendered

    # --- Gap 3: diamond reuse of a shared sub-stack must not be flagged cyclic ---
    def test_diamond_shared_substack_not_cyclic(self, tmp_project):
        from copilot_memory.store import upsert_stack, assemble_stack

        self._write(tmp_project, self._mk("s", decisions=["S"]))
        self._write(tmp_project, self._mk("a", decisions=["A"]))
        self._write(tmp_project, self._mk("b", decisions=["B"]))
        upsert_stack(tmp_project, "shared", ["s"], "t")
        upsert_stack(tmp_project, "left", ["@shared", "a"], "t")
        upsert_stack(tmp_project, "right", ["@shared", "b"], "t")

        # Both branches legitimately reuse @shared — must resolve, not raise.
        _, structured = assemble_stack(tmp_project, ["@left", "@right"])
        assert structured["layers"] == ["s", "a", "s", "b"]
        assert structured["decisions"] == ["S", "A", "B"]  # base-first dedupe

    def test_true_cycle_still_raises_after_unwind_fix(self, tmp_project):
        from copilot_memory.store import upsert_stack, assemble_stack

        self._write(tmp_project, self._mk("a"))
        upsert_stack(tmp_project, "x", ["@y", "a"], "t")
        upsert_stack(tmp_project, "y", ["@x"], "t")
        with pytest.raises(ValueError, match="[Cc]yclic|too deep"):
            assemble_stack(tmp_project, ["@x"])

    # --- Gap 4: save-time ref validation (warn, non-blocking) ---
    def test_unresolved_stack_refs(self, tmp_project):
        from copilot_memory.store import unresolved_stack_refs

        self._write(tmp_project, self._mk("real"))
        bad = unresolved_stack_refs(tmp_project, ["real", "ghost", "@nostack"])
        assert "real" not in bad
        assert "ghost" in bad
        assert "@nostack" in bad

    # --- Gap 5: malformed stacks.yml warns instead of vanishing silently ---
    def test_malformed_stacks_warns(self, tmp_project, capsys):
        from copilot_memory.store import load_stacks

        (tmp_project / "stacks.yml").write_text(
            "schema_version: 1\nstacks: not-a-list\n", encoding="utf-8")
        result = load_stacks(tmp_project)
        assert result.stacks == []
        assert "malformed" in capsys.readouterr().err

    # --- Gap 7: ambiguous repo prefix warns but stays deterministic ---
    def test_ambiguous_repo_prefix_warns(self, tmp_path, monkeypatch, capsys):
        from copilot_memory import store as store_mod

        root = tmp_path / "memroot"
        root.mkdir()
        (root / "foo-11111111").mkdir()
        (root / "foo-22222222").mkdir()
        monkeypatch.setattr(store_mod, "MEMORY_ROOT", root)

        result = store_mod.find_project_dir_by_name("foo")
        assert result is not None
        assert result.name == "foo-11111111"  # deterministic: first sorted
        assert "ambiguous" in capsys.readouterr().err

    # --- Gap 9: verify reports dangling stack refs ---
    def test_check_stack_integrity_reports_dangling(self, tmp_project):
        from copilot_memory.store import upsert_stack, check_stack_integrity

        self._write(tmp_project, self._mk("real"))
        upsert_stack(tmp_project, "mix", ["real", "ghost"], "t")
        problems = check_stack_integrity(tmp_project)
        assert any("ghost" in p for p in problems)
        assert all("real (unresolvable)" not in p for p in problems)

    # --- Auto-refresh: fingerprint source layers at apply, detect staleness ---
    def test_apply_records_source_version_fingerprint(self, tmp_project):
        from copilot_memory.store import apply_stack

        self._write(tmp_project, self._mk("base", lastUpdatedAt="2026-06-01T00:00:00Z"))
        self._write(tmp_project, self._mk("top", lastUpdatedAt="2026-06-02T00:00:00Z"))
        merged, _ = apply_stack(
            tmp_project, ["base", "top"],
            new_session_id="applied-fp", now_iso_str="2026-06-10T00:00:00Z")
        assert merged.sourceVersions == {
            "base": "2026-06-01T00:00:00Z",
            "top": "2026-06-02T00:00:00Z",
        }

    def test_stack_is_stale_fresh_returns_empty(self, tmp_project):
        from copilot_memory.store import apply_stack, stack_is_stale

        self._write(tmp_project, self._mk("base"))
        self._write(tmp_project, self._mk("top"))
        merged, _ = apply_stack(
            tmp_project, ["base", "top"],
            new_session_id="applied-fresh", now_iso_str="2026-06-10T00:00:00Z")
        assert stack_is_stale(tmp_project, merged) == []

    def test_stack_is_stale_detects_updated_layer(self, tmp_project):
        from copilot_memory.store import apply_stack, stack_is_stale

        self._write(tmp_project, self._mk("base", lastUpdatedAt="2026-06-01T00:00:00Z"))
        self._write(tmp_project, self._mk("top", lastUpdatedAt="2026-06-01T00:00:00Z"))
        merged, _ = apply_stack(
            tmp_project, ["base", "top"],
            new_session_id="applied-stale", now_iso_str="2026-06-10T00:00:00Z")
        # A source layer moves on after the apply.
        self._write(tmp_project, self._mk(
            "top", decisions=["new work"], lastUpdatedAt="2026-06-15T00:00:00Z"))
        assert stack_is_stale(tmp_project, merged) == ["top"]

    def test_stack_is_stale_flags_missing_layer(self, tmp_project):
        from copilot_memory.store import apply_stack, stack_is_stale

        self._write(tmp_project, self._mk("base"))
        self._write(tmp_project, self._mk("gone"))
        merged, _ = apply_stack(
            tmp_project, ["base", "gone"],
            new_session_id="applied-miss", now_iso_str="2026-06-10T00:00:00Z")
        (tmp_project / "sessions" / "_default" / "gone.json").unlink()
        assert stack_is_stale(tmp_project, merged) == ["gone"]

    def test_stack_is_stale_unknown_for_pre_feature_snapshot(self, tmp_project):
        from copilot_memory.store import stack_is_stale

        legacy = self._mk("legacy-merged", parents=["base", "top"])
        assert legacy.sourceVersions == {}
        assert stack_is_stale(tmp_project, legacy) is None

    def test_refresh_stack_rebuilds_when_stale(self, tmp_project):
        from copilot_memory.store import apply_stack, refresh_stack, load_session

        self._write(tmp_project, self._mk("base", decisions=["b-old"]))
        self._write(tmp_project, self._mk("top", decisions=["t-old"]))
        merged, path = apply_stack(
            tmp_project, ["base", "top"],
            new_session_id="applied-rb", now_iso_str="2026-06-10T00:00:00Z")
        assert "t-new" not in merged.decisions

        self._write(tmp_project, self._mk(
            "top", decisions=["t-old", "t-new"], lastUpdatedAt="2026-06-20T00:00:00Z"))

        rebuilt, new_path, stale = refresh_stack(
            tmp_project, merged, "2026-06-21T00:00:00Z")
        assert stale == ["top"]
        assert rebuilt.sessionId == "applied-rb"       # rebuilt in place
        assert "t-new" in rebuilt.decisions
        # Fingerprint re-stamped, so it is now fresh again.
        assert load_session(new_path).sourceVersions["top"] == "2026-06-20T00:00:00Z"

    def test_refresh_stack_noop_when_fresh(self, tmp_project):
        from copilot_memory.store import apply_stack, refresh_stack

        self._write(tmp_project, self._mk("base"))
        merged, _ = apply_stack(
            tmp_project, ["base"],
            new_session_id="applied-noop", now_iso_str="2026-06-10T00:00:00Z")
        rebuilt, path, stale = refresh_stack(tmp_project, merged, "2026-06-11T00:00:00Z")
        assert stale == []
        assert path is None
        assert rebuilt is merged




