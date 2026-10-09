"""Integration tests for the copilot-memory CLI commands."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from copilot_memory.cli import cmd_status, cmd_verify, cmd_compact, cmd_init, cmd_schema_fix
from copilot_memory.store import _write_yaml, _write_json, MEMORY_ROOT


class FakeArgs:
    """Minimal args namespace for testing CLI commands."""
    def __init__(self, **kwargs):
        self.cwd = kwargs.get("cwd", None)
        self.fix = kwargs.get("fix", False)
        self.target = kwargs.get("target", "stdout")


@pytest.fixture
def mock_memory(tmp_path):
    """Create a complete mock project memory structure."""
    project_dir = tmp_path / "test-project-abc12345"
    project_dir.mkdir()

    # Core files
    _write_yaml(project_dir / "preferences.yml", {
        "schema_version": 1,
        "language": "python",
    })
    _write_yaml(project_dir / "rules.yml", {
        "schema_version": 1,
        "rules": [
            {
                "id": "use-python",
                "type": "do",
                "description": "Use Python",
                "learned_from": "explicit instruction",
                "created_at": "2026-06-11",
                "last_used": "2026-06-11",
                "use_count": 1,
                "share": False,
            },
        ],
    })
    _write_yaml(project_dir / "context.yml", {
        "schema_version": 1,
        "name": "TestProject",
        "description": "A test project",
        "stack": ["Python", "FastAPI"],
        "key_files": [],
        "notes": "",
    })
    _write_yaml(project_dir / "tracking.yml", {
        "schema_version": 1,
        "hotspots": [],
        "common_errors": [],
    })

    # Sessions
    sessions_dir = project_dir / "sessions" / "_default"
    sessions_dir.mkdir(parents=True)

    sid = "test-session-001"
    _write_json(sessions_dir / f"{sid}.json", {
        "sessionId": sid,
        "status": "active",
        "startedAt": "2026-06-11T10:00:00Z",
        "lastUpdatedAt": "2026-06-11T10:30:00Z",
        "summary": "Test session",
        "filesChanged": [],
        "decisions": [],
        "learnings": [],
    })
    _write_json(project_dir / "sessions" / "latest.json", {
        "lastSessionId": sid,
        "lastUpdatedAt": "2026-06-11T10:30:00Z",
        "activeSession": None,
    })

    # Global dir
    global_dir = tmp_path / "_global"
    global_dir.mkdir()
    _write_yaml(global_dir / "preferences.yml", {"schema_version": 1})
    _write_yaml(global_dir / "rules.yml", {"schema_version": 1, "rules": []})

    return tmp_path, project_dir


class TestCmdVerify:
    def test_verify_clean_project(self, mock_memory, capsys):
        tmp_path, project_dir = mock_memory

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir), \
             patch("copilot_memory.cli.GLOBAL_DIR", tmp_path / "_global"):
            code = cmd_verify(FakeArgs())

        assert code == 0
        output = capsys.readouterr().out
        assert "All checks passed" in output

    def test_verify_detects_missing_schema(self, mock_memory, capsys):
        tmp_path, project_dir = mock_memory

        # Remove schema_version from a file
        data = yaml.safe_load((project_dir / "rules.yml").read_text(encoding="utf-8"))
        del data["schema_version"]
        (project_dir / "rules.yml").write_text(
            yaml.dump(data), encoding="utf-8"
        )

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_verify(FakeArgs())

        # Missing schema_version is a warning, not a hard error
        output = capsys.readouterr().out
        assert "schema_version" in output

    def test_verify_fix_adds_schema(self, mock_memory, capsys):
        tmp_path, project_dir = mock_memory

        # Remove schema_version
        data = yaml.safe_load((project_dir / "rules.yml").read_text(encoding="utf-8"))
        del data["schema_version"]
        (project_dir / "rules.yml").write_text(
            yaml.dump(data), encoding="utf-8"
        )

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_verify(FakeArgs(fix=True))

        assert code == 0
        # Verify it was actually fixed
        fixed = yaml.safe_load((project_dir / "rules.yml").read_text(encoding="utf-8"))
        assert fixed["schema_version"] == 1

    def test_verify_detects_dangling_session(self, mock_memory, capsys):
        tmp_path, project_dir = mock_memory

        # Point latest to nonexistent session
        _write_json(project_dir / "sessions" / "latest.json", {
            "lastSessionId": "nonexistent-id",
            "lastUpdatedAt": "2026-06-11",
        })

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_verify(FakeArgs())

        assert code == 1
        output = capsys.readouterr().out
        assert "Dangling" in output


class TestCmdCompact:
    def test_compact_prunes_excess_sessions(self, mock_memory, capsys):
        tmp_path, project_dir = mock_memory
        default_dir = project_dir / "sessions" / "_default"

        # Create 15 sessions (cap is 10)
        for i in range(15):
            _write_json(default_dir / f"session-{i:03d}.json", {
                "sessionId": f"session-{i:03d}",
                "status": "closed",
            })

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_compact(FakeArgs())

        assert code == 0
        remaining = list(default_dir.glob("*.json"))
        assert len(remaining) <= 11  # 10 cap + the original test-session-001

    def test_compact_nothing_to_do(self, mock_memory, capsys):
        tmp_path, project_dir = mock_memory

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_compact(FakeArgs())

        assert code == 0
        output = capsys.readouterr().out
        assert "Nothing to compact" in output


class TestCmdInit:
    def test_init_creates_project(self, tmp_path, capsys):
        work_dir = tmp_path / "new-project"
        work_dir.mkdir()

        with patch("copilot_memory.cli.find_project_dir", return_value=None), \
             patch("copilot_memory.cli.ensure_project_dir") as mock_ensure:
            project_dir = tmp_path / "new-project-12345678"
            project_dir.mkdir()
            mock_ensure.return_value = project_dir

            with patch("copilot_memory.store.TEMPLATE_DIR", tmp_path / "_no_template"):
                code = cmd_init(FakeArgs(cwd=str(work_dir)))

        assert code == 0
        output = capsys.readouterr().out
        assert "Project memory created" in output

    def test_init_skips_if_exists(self, mock_memory, capsys):
        tmp_path, project_dir = mock_memory

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_init(FakeArgs())

        assert code == 0
        output = capsys.readouterr().out
        assert "already exists" in output


class TestCmdSchemaFix:
    def test_fixes_missing_schema_versions(self, tmp_path, capsys):
        # Create files without schema_version
        (tmp_path / "prefs.yml").write_text("language: python\n", encoding="utf-8")
        (tmp_path / "rules.yml").write_text("rules: []\n", encoding="utf-8")

        code = cmd_schema_fix(FakeArgs(cwd=str(tmp_path)))

        assert code == 0
        output = capsys.readouterr().out
        assert "Fixed 2 file(s)" in output

        # Verify fix
        for fname in ["prefs.yml", "rules.yml"]:
            data = yaml.safe_load((tmp_path / fname).read_text(encoding="utf-8"))
            assert data["schema_version"] == 1

    def test_skips_already_valid(self, tmp_path, capsys):
        _write_yaml(tmp_path / "test.yml", {"schema_version": 1, "key": "val"})

        code = cmd_schema_fix(FakeArgs(cwd=str(tmp_path)))

        assert code == 0
        output = capsys.readouterr().out
        assert "already have schema_version" in output


class SessionCheckArgs:
    def __init__(self, cwd=None, path=None, session_id=None):
        self.cwd = cwd
        self.path = path
        self.session_id = session_id


class TestCmdSessionCheckSize:
    def test_within_limits_returns_zero(self, mock_memory, capsys):
        from copilot_memory.cli import cmd_session_check_size

        tmp_path, project_dir = mock_memory
        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_session_check_size(SessionCheckArgs())
        out = capsys.readouterr().out
        assert code == 0
        assert "within limits" in out

    def test_over_threshold_returns_one(self, mock_memory, capsys):
        from copilot_memory.cli import cmd_session_check_size

        tmp_path, project_dir = mock_memory
        # Bloat the existing session
        sid = "test-session-001"
        path = project_dir / "sessions" / "_default" / f"{sid}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["decisions"] = [f"d{i}" for i in range(15)]
        data["learnings"] = [f"l{i}" for i in range(10)]
        path.write_text(json.dumps(data), encoding="utf-8")

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_session_check_size(SessionCheckArgs())
        out = capsys.readouterr().out
        assert code == 1
        assert "compaction recommended" in out

    def test_explicit_path_wins(self, mock_memory, capsys, tmp_path):
        from copilot_memory.cli import cmd_session_check_size

        _, project_dir = mock_memory
        big = tmp_path / "big.json"
        big.write_text(json.dumps({
            "sessionId": "big",
            "status": "active",
            "filesChanged": [f"f{i}.py" for i in range(50)],
        }), encoding="utf-8")

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_session_check_size(SessionCheckArgs(path=str(big)))
        assert code == 1

    def test_missing_session_returns_two(self, mock_memory, capsys, tmp_path):
        from copilot_memory.cli import cmd_session_check_size

        _, project_dir = mock_memory
        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_session_check_size(SessionCheckArgs(path=str(tmp_path / "nope.json")))
        assert code == 2


class MergeArgs:
    def __init__(self, sids, cwd=None, into=None, new_id=None, dry_run=False):
        self.sids = sids
        self.cwd = cwd
        self.into = into
        self.new_id = new_id
        self.dry_run = dry_run


class TestCmdSessionMerge:
    def _write_extra_session(self, project_dir, sid, **fields):
        payload = {
            "sessionId": sid,
            "status": "active",
            "startedAt": "2026-06-01T00:00:00Z",
            "lastUpdatedAt": "2026-06-01T00:00:00Z",
            "summary": fields.get("summary", ""),
            "filesChanged": fields.get("filesChanged", []),
            "decisions": fields.get("decisions", []),
            "learnings": fields.get("learnings", []),
        }
        _write_json(project_dir / "sessions" / "_default" / f"{sid}.json", payload)

    def test_merge_creates_new_session(self, mock_memory, capsys):
        from copilot_memory.cli import cmd_session_merge

        tmp_path, project_dir = mock_memory
        self._write_extra_session(project_dir, "extra-1", filesChanged=["x.py"])

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_session_merge(MergeArgs(
                sids=["test-session-001", "extra-1"],
                new_id="merged-1",
            ))
        out = capsys.readouterr().out
        assert code == 0
        assert "Merged" in out
        merged_path = project_dir / "sessions" / "_default" / "merged-1.json"
        assert merged_path.exists()
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        assert data["parents"] == ["test-session-001", "extra-1"]
        assert "x.py" in data["filesChanged"]

    def test_merge_dry_run_writes_nothing(self, mock_memory, capsys):
        from copilot_memory.cli import cmd_session_merge

        tmp_path, project_dir = mock_memory
        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_session_merge(MergeArgs(
                sids=["test-session-001"],
                new_id="preview-1",
                dry_run=True,
            ))
        assert code == 0
        out = capsys.readouterr().out
        assert "dry-run" in out
        assert not (project_dir / "sessions" / "_default" / "preview-1.json").exists()

    def test_merge_missing_parent_returns_two(self, mock_memory, capsys):
        from copilot_memory.cli import cmd_session_merge

        tmp_path, project_dir = mock_memory
        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_session_merge(MergeArgs(
                sids=["nonexistent"],
                new_id="x",
            ))
        assert code == 2
        assert "Unknown session" in capsys.readouterr().out


class TestCmdSessionStackAndList:
    def test_session_list_current_repo(self, mock_memory, capsys):
        from copilot_memory.cli import cmd_session_list
        from types import SimpleNamespace
        tmp_path, project_dir = mock_memory
        args = SimpleNamespace(cwd=None, repo=None, all_repos=False)
        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir):
            code = cmd_session_list(args)
        out = capsys.readouterr().out
        assert code == 0
        assert "test-session-001" in out
        assert "Test session" in out

    def test_stack_save_show_and_list(self, mock_memory, capsys):
        from copilot_memory.cli import cmd_session_stack
        from types import SimpleNamespace
        tmp_path, project_dir = mock_memory
        gdir = tmp_path / "_global"
        save = SimpleNamespace(cwd=None, stack_action="save", name="common",
                               sids=["test-session-001"], append=False,
                               description="everyday", global_=False)
        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir), \
             patch("copilot_memory.cli.GLOBAL_DIR", gdir), \
             patch("copilot_memory.store.GLOBAL_DIR", gdir):
            assert cmd_session_stack(save) == 0
            show = SimpleNamespace(cwd=None, stack_action="show", stack="common",
                                   sids=[], json=False)
            assert cmd_session_stack(show) == 0
            out = capsys.readouterr().out
            assert "Layered context" in out
            lst = SimpleNamespace(cwd=None, stack_action="list", global_=False)
            assert cmd_session_stack(lst) == 0
            assert "common" in capsys.readouterr().out

    def test_stack_show_unknown_returns_two(self, mock_memory, capsys):
        from copilot_memory.cli import cmd_session_stack
        from types import SimpleNamespace
        tmp_path, project_dir = mock_memory
        gdir = tmp_path / "_global"
        show = SimpleNamespace(cwd=None, stack_action="show", stack="ghost",
                               sids=[], json=False)
        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir), \
             patch("copilot_memory.cli.GLOBAL_DIR", gdir), \
             patch("copilot_memory.store.GLOBAL_DIR", gdir):
            assert cmd_session_stack(show) == 2
        assert "Unknown stack" in capsys.readouterr().out

    def test_stack_refresh_check_and_rebuild(self, mock_memory, capsys):
        from copilot_memory.cli import cmd_session_stack
        from copilot_memory.store import _write_json, load_session, find_session_file
        from types import SimpleNamespace
        tmp_path, project_dir = mock_memory
        gdir = tmp_path / "_global"

        with patch("copilot_memory.cli.find_project_dir", return_value=project_dir), \
             patch("copilot_memory.cli.GLOBAL_DIR", gdir), \
             patch("copilot_memory.store.GLOBAL_DIR", gdir):
            # Materialize a 1-layer stack from the mock session.
            apply = SimpleNamespace(cwd=None, stack_action="apply", stack=None,
                                    sids=["test-session-001"], into=None,
                                    new_id="applied-cli")
            assert cmd_session_stack(apply) == 0
            capsys.readouterr()

            # Fresh → --check exits 0.
            check = SimpleNamespace(cwd=None, stack_action="refresh",
                                    session_id="applied-cli", check=True, into=None)
            assert cmd_session_stack(check) == 0
            assert "fresh" in capsys.readouterr().out.lower()

            # Bump the source layer so the materialized stack is now stale.
            src = find_session_file(project_dir, "test-session-001")
            data = load_session(src).model_dump()
            data["lastUpdatedAt"] = "2099-01-01T00:00:00Z"
            data["decisions"] = ["brand new decision"]
            _write_json(src, data)

            # Stale → --check exits 1.
            assert cmd_session_stack(check) == 1
            assert "stale" in capsys.readouterr().out.lower()

            # Rebuild → exits 0 and picks up the new decision.
            refresh = SimpleNamespace(cwd=None, stack_action="refresh",
                                      session_id="applied-cli", check=False, into=None)
            assert cmd_session_stack(refresh) == 0
            assert "Refreshed" in capsys.readouterr().out
            rebuilt = load_session(find_session_file(project_dir, "applied-cli"))
            assert "brand new decision" in rebuilt.decisions
