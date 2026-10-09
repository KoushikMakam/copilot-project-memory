"""CLI for Copilot Memory — safety-net for complex operations.

Simple operations (read/list/add rules) are handled by the AI inline.
This tool handles: verify, compact, init, repair, export, status.

Usage:
  copilot-memory status              Show project memory health
  copilot-memory verify [--fix]      Check integrity, optionally repair
  copilot-memory compact             Enforce storage caps, prune stale data
  copilot-memory init                Create project memory for current dir
  copilot-memory export [team]       Export rules for team sharing
  copilot-memory schema-fix          Add schema_version to all YAML files
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copilot_memory.models import (
    ContextFile,
    LatestSession,
    Rule,
    RulesFile,
    SessionEntry,
    VerifyReport,
    FileCheck,
    now_iso,
)
from copilot_memory.store import (
    EXPECTED_FILES,
    GLOBAL_DIR,
    MEMORY_ROOT,
    TEMPLATE_DIR,
    archive_closed_sessions,
    assemble_stack,
    apply_stack,
    refresh_stack,
    stack_is_stale,
    check_session_integrity,
    check_stack_integrity,
    ensure_project_dir,
    find_project_dir,
    find_project_dir_by_name,
    find_session_file,
    find_stack,
    get_dir_size,
    list_sessions,
    load_context,
    load_latest_session,
    load_prefs,
    load_rules,
    load_session,
    load_stacks,
    load_global_stacks,
    merge_sessions,
    remove_from_stack,
    save_rules,
    save_context,
    save_prefs,
    save_latest_session,
    session_needs_compaction,
    unresolved_stack_refs,
    upsert_stack,
    _read_yaml,
    _write_yaml,
    _read_json,
    _write_json,
)


# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _no_color() -> bool:
    return os.environ.get("NO_COLOR") is not None or not sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if _no_color():
        return text
    return f"{code}{text}{RESET}"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    """Show project memory health overview."""
    project_dir = find_project_dir(args.cwd)

    # Global stats
    global_rules = load_rules(GLOBAL_DIR) if GLOBAL_DIR.exists() else RulesFile()
    global_prefs = load_prefs(GLOBAL_DIR) if GLOBAL_DIR.exists() else {}
    global_pref_count = len([k for k in global_prefs if k != "schema_version"])

    print(f"\n{_c(BOLD + CYAN, '🧠 Copilot Project Memory — Status')}")
    print(f"{'─' * 45}")

    print(f"\n{_c(BOLD, '🌍 Global:')}")
    print(f"  Rules: {len(global_rules.rules)}")
    print(f"  Preferences: {global_pref_count}")

    if not project_dir:
        print(f"\n{_c(YELLOW, '⚠️  No project memory found for this directory.')}")
        print(f"  Run: {_c(CYAN, 'copilot-memory init')} to create one.\n")
        return 0

    # Project stats
    rules = load_rules(project_dir)
    prefs = load_prefs(project_dir)
    pref_count = len([k for k in prefs if k != "schema_version"])
    context = load_context(project_dir)
    sessions = list_sessions(project_dir)
    latest = load_latest_session(project_dir)
    dangling, mismatched = check_session_integrity(project_dir)
    total_size = get_dir_size(project_dir)

    print(f"\n{_c(BOLD, f'📂 Project: {context.name or project_dir.name}')}")
    print(f"  Rules: {len(rules.rules)}")
    print(f"  Preferences: {pref_count}")
    print(f"  Sessions: {len(sessions)}")
    if context.stack:
        print(f"  Stack: {', '.join(context.stack)}")
    print(f"  Size: {total_size / 1024:.1f} KB")

    # Health indicators
    print(f"\n{_c(BOLD, '🏥 Health:')}")
    issues = 0

    # Check for missing files
    for fname in EXPECTED_FILES:
        fpath = project_dir / fname
        if not fpath.exists():
            print(f"  {_c(YELLOW, '⚠️')} Missing: {fname}")
            issues += 1

    # Check schema versions
    for fname in EXPECTED_FILES:
        fpath = project_dir / fname
        if fpath.exists():
            data = _read_yaml(fpath)
            if "schema_version" not in data:
                print(f"  {_c(YELLOW, '⚠️')} No schema_version: {fname}")
                issues += 1

    # Check session integrity
    for d in dangling:
        print(f"  {_c(RED, '❌')} Dangling: {d}")
        issues += 1
    for m in mismatched:
        print(f"  {_c(RED, '❌')} Mismatch: {m}")
        issues += 1

    if issues == 0:
        print(f"  {_c(GREEN, '✅ All checks passed')}")
    else:
        print(f"\n  {_c(YELLOW, f'⚠️  {issues} issue(s) found.')} Run: copilot-memory verify --fix")

    # Last session
    if latest and sessions:
        last = sessions[0][1]
        print(f"\n{_c(BOLD, '📝 Last session:')}")
        print(f"  {last.summary or '(no summary)'}")
        print(f"  Status: {last.status} | Updated: {last.lastUpdatedAt[:10] if last.lastUpdatedAt else 'unknown'}")
        if last.compactionCount:
            print(f"  🗜️  Compactions: {last.compactionCount}")
        needs, reasons = session_needs_compaction(last)
        if needs:
            print(f"  {_c(YELLOW, '⚠️  Ready for compaction:')} {'; '.join(reasons)}")
        if latest.activeSession:
            print(f"  📌 Active named session: {latest.activeSession}")

    print()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Check integrity of all memory files, optionally repair."""
    project_dir = find_project_dir(args.cwd)
    if not project_dir:
        print(f"{_c(RED, '❌ No project memory found.')} Run: copilot-memory init")
        return 1

    report = VerifyReport(project=project_dir.name)
    fix = args.fix

    print(f"\n{_c(BOLD + CYAN, '🔍 Memory Integrity Check')}")
    print(f"  Project: {project_dir.name}")
    print(f"  Mode: {'fix' if fix else 'check only'}\n")

    # 1. Check expected files
    for fname in EXPECTED_FILES:
        fpath = project_dir / fname
        if not fpath.exists():
            if fix:
                # Recreate from template
                template = TEMPLATE_DIR / fname
                if template.exists():
                    data = _read_yaml(template)
                    data["schema_version"] = 1
                    _write_yaml(fpath, data)
                    status = "recreated"
                    detail = f"Recreated from template"
                else:
                    _write_yaml(fpath, {"schema_version": 1})
                    status = "recreated"
                    detail = "Created empty with schema_version"
                print(f"  {_c(YELLOW, '⚠️')} {fname} — {detail}")
            else:
                status = "missing"
                detail = "File not found"
                print(f"  {_c(RED, '❌')} {fname} — missing")
        else:
            # Validate content
            data = _read_yaml(fpath)
            if not data:
                status = "malformed"
                detail = "Empty or invalid YAML"
                print(f"  {_c(RED, '❌')} {fname} — {detail}")
            elif "schema_version" not in data:
                if fix:
                    data["schema_version"] = 1
                    _write_yaml(fpath, data)
                    status = "ok"
                    detail = "Added schema_version"
                    print(f"  {_c(GREEN, '✅')} {fname} (fixed: added schema_version)")
                else:
                    status = "ok"
                    detail = "Missing schema_version"
                    print(f"  {_c(YELLOW, '⚠️')} {fname} — no schema_version")
            else:
                status = "ok"
                detail = f"Valid (schema v{data['schema_version']})"
                print(f"  {_c(GREEN, '✅')} {fname} ({detail})")

            # Validate rules.yml specifically
            if fname == "rules.yml" and status == "ok":
                try:
                    load_rules(project_dir)
                except Exception as e:
                    detail = f"Validation error: {e}"
                    status = "malformed"
                    print(f"  {_c(RED, '   ↳ ❌')} {detail}")

        report.checks.append(FileCheck(path=fname, status=status, detail=detail))

    # 2. Check sessions
    print()
    dangling, mismatched = check_session_integrity(project_dir)
    report.dangling_sessions = dangling
    report.mismatched_ids = mismatched

    if dangling:
        for d in dangling:
            print(f"  {_c(RED, '❌')} Dangling session: {d}")
        if fix:
            # Clear latest.json to remove dangling pointer
            latest_path = project_dir / "sessions" / "latest.json"
            if latest_path.exists():
                _write_json(latest_path, {
                    "lastSessionId": "",
                    "lastUpdatedAt": now_iso(),
                    "activeSession": None,
                })
                print(f"  {_c(GREEN, '  ↳ ✅')} Reset latest.json")

    if mismatched:
        for m in mismatched:
            print(f"  {_c(RED, '❌')} ID mismatch: {m}")
        if fix:
            # Rename files to match their sessionId
            sessions_dir = project_dir / "sessions"
            for path in sessions_dir.rglob("*.json"):
                if path.name == "latest.json":
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    sid = data.get("sessionId", "")
                    if sid and sid != path.stem:
                        new_path = path.parent / f"{sid}.json"
                        if not new_path.exists():
                            path.rename(new_path)
                            print(f"  {_c(GREEN, '  ↳ ✅')} Renamed {path.name} → {sid}.json")
                except Exception:
                    continue

    if not dangling and not mismatched:
        print(f"  {_c(GREEN, '✅')} Sessions: no integrity issues")

    # 2b. Check stacks for dangling references
    stack_problems = check_stack_integrity(project_dir)
    report.dangling_stack_refs = stack_problems
    if stack_problems:
        for p in stack_problems:
            print(f"  {_c(RED, '❌')} Dangling stack ref: {p}")
    else:
        print(f"  {_c(GREEN, '✅')} Stacks: no dangling references")

    # 3. Summary
    report.total_size_bytes = get_dir_size(project_dir)
    errors = sum(1 for c in report.checks if c.status in ("missing", "malformed"))
    errors += len(dangling) + len(mismatched) + len(stack_problems)

    print(f"\n{'─' * 45}")
    if errors == 0:
        print(f"  {_c(GREEN + BOLD, '✅ All checks passed')}")
    elif fix:
        print(f"  {_c(YELLOW + BOLD, f'⚠️  {errors} issue(s) found and repaired')}")
    else:
        print(f"  {_c(RED + BOLD, f'❌ {errors} issue(s) found')} — run with --fix to repair")

    print(f"  📦 Total memory size: {report.total_size_bytes / 1024:.1f} KB\n")
    return 0 if errors == 0 else 1


def cmd_compact(args: argparse.Namespace) -> int:
    """Enforce storage caps and prune stale data."""
    project_dir = find_project_dir(args.cwd)
    if not project_dir:
        print(f"{_c(RED, '❌ No project memory found.')}")
        return 1

    print(f"\n{_c(BOLD + CYAN, '📊 Compact: Enforcing storage caps')}\n")
    actions = 0

    def _all_sessions(folder: Path) -> list[Path]:
        return sorted(
            [p for p in folder.iterdir() if p.is_file()
             and (p.suffix == ".json" or p.name.endswith(".json.gz"))
             and p.name != "latest.json"],
            key=lambda p: p.stat().st_mtime,
        )

    # 0. Archive closed sessions older than 7 days (gzip in place)
    archived = archive_closed_sessions(project_dir, older_than_days=7)
    if archived:
        saved = sum(orig - gz for _, _, orig, gz in archived)
        for _, gz_path, orig, gz in archived:
            pct = int(100 * (1 - gz / orig)) if orig else 0
            print(f"  {_c(GREEN, '🗜️ ')} Archived {gz_path.name} ({orig}B → {gz}B, -{pct}%)")
        print(f"  {_c(GREEN, f'    ↳ saved {saved} bytes total')}")
        actions += len(archived)

    # 1. Cap default sessions at 10
    default_dir = project_dir / "sessions" / "_default"
    if default_dir.exists():
        sessions = _all_sessions(default_dir)
        if len(sessions) > 10:
            to_remove = sessions[:len(sessions) - 10]
            for s in to_remove:
                s.unlink()
                print(f"  {_c(GREEN, '✅')} Pruned old session: {s.name}")
                actions += 1

    # 2. Cap named session entries at 20 each
    sessions_dir = project_dir / "sessions"
    if sessions_dir.exists():
        for subdir in sessions_dir.iterdir():
            if subdir.is_dir() and subdir.name != "_default":
                entries = _all_sessions(subdir)
                if len(entries) > 20:
                    to_remove = entries[:len(entries) - 20]
                    for e in to_remove:
                        e.unlink()
                        print(f"  {_c(GREEN, '✅')} Pruned {subdir.name}/{e.name}")
                        actions += 1

    # 3. Cap tracking hotspots at 5
    tracking_path = project_dir / "tracking.yml"
    if tracking_path.exists():
        data = _read_yaml(tracking_path)
        hotspots = data.get("hotspots", [])
        if isinstance(hotspots, list) and len(hotspots) > 5:
            hotspots.sort(key=lambda h: h.get("touch_count", 0), reverse=True)
            data["hotspots"] = hotspots[:5]
            _write_yaml(tracking_path, data)
            print(f"  {_c(GREEN, '✅')} Pruned hotspots: kept top 5")
            actions += 1

        errors = data.get("common_errors", [])
        if isinstance(errors, list) and len(errors) > 10:
            data["common_errors"] = errors[-10:]
            _write_yaml(tracking_path, data)
            print(f"  {_c(GREEN, '✅')} Pruned common_errors: kept latest 10")
            actions += 1

    # 4. Report stale rules (never auto-delete)
    rules = load_rules(project_dir)
    stale_rules = []
    now = datetime.now(timezone.utc)
    for rule in rules.rules:
        if rule.last_used:
            try:
                last = datetime.fromisoformat(rule.last_used.replace("Z", "+00:00"))
                days = (now - last).days
                if days > 30:
                    stale_rules.append((rule.id, days))
            except (ValueError, TypeError):
                pass

    if stale_rules:
        print(f"\n  {_c(YELLOW, '💡 Possibly stale rules (not used in 30+ days):')}")
        for rule_id, days in stale_rules:
            print(f"    - [{rule_id}] last used: {days} days ago")
        print(f"\n  Use :forget <id> to remove, or :rules touch <id> to keep.")

    if actions == 0 and not stale_rules:
        print(f"  {_c(GREEN, '✅ Nothing to compact — all within limits.')}")

    print()
    return 0


def cmd_session_archive(args: argparse.Namespace) -> int:
    """Gzip closed sessions older than N days."""
    project_dir = find_project_dir(args.cwd)
    if not project_dir:
        print(f"{_c(RED, '❌ No project memory found.')}")
        return 2

    days = getattr(args, "older_than_days", 7)
    archived = archive_closed_sessions(project_dir, older_than_days=days)
    if not archived:
        print(f"{_c(GREEN, f'✅ Nothing to archive (no closed sessions older than {days} days).')}")
        return 0

    saved = 0
    for _, gz_path, orig, gz in archived:
        pct = int(100 * (1 - gz / orig)) if orig else 0
        saved += orig - gz
        print(f"  {_c(GREEN, '🗜️ ')} {gz_path.name} ({orig}B → {gz}B, -{pct}%)")
    print(f"\n  {_c(GREEN, f'✅ Archived {len(archived)} session(s), saved {saved} bytes.')}")
    return 0


def cmd_session_merge(args: argparse.Namespace) -> int:
    """Merge multiple parent sessions into a new session."""
    project_dir = find_project_dir(args.cwd)
    if not project_dir:
        print(f"{_c(RED, '❌ No project memory found.')}")
        return 2

    parent_ids = list(getattr(args, "sids", []) or [])
    if len(parent_ids) < 1:
        print(f"{_c(RED, '❌ Provide at least one parent session id.')}")
        return 2

    new_sid = getattr(args, "new_id", None) or str(uuid.uuid4())
    try:
        merged, path = merge_sessions(
            project_dir,
            parent_ids=parent_ids,
            new_session_id=new_sid,
            now_iso_str=now_iso(),
            into_name=getattr(args, "into", None),
            dry_run=getattr(args, "dry_run", False),
        )
    except ValueError as e:
        print(f"{_c(RED, '❌')} {e}")
        return 2

    if getattr(args, "dry_run", False):
        print(f"{_c(BOLD + CYAN, '🔍 Merge preview (dry-run):')}")
        print(f"  new sessionId: {merged.sessionId}")
        print(f"  parents: {', '.join(merged.parents)}")
        print(f"  filesChanged: {len(merged.filesChanged)}")
        print(f"  decisions (verbatim): {len(merged.decisions)}")
        print(f"  learnings (verbatim): {len(merged.learnings)}")
        print(f"  compactionCount: {merged.compactionCount}")
        return 0

    print(f"{_c(GREEN, '✅ Merged')} {len(merged.parents)} session(s) → {path}")
    print(f"  sessionId: {merged.sessionId}")
    print(f"  parents: {', '.join(merged.parents)}")
    print(f"  files: {len(merged.filesChanged)}, decisions: {len(merged.decisions)}, learnings: {len(merged.learnings)}")
    return 0


def cmd_session_check_size(args: argparse.Namespace) -> int:
    """Return exit 1 when the target session crosses any compaction threshold.

    Target resolution order:
      1. --path <file>    (explicit)
      2. --session-id <id> (searched in project sessions/)
      3. latest.json      (default)
    """
    project_dir = find_project_dir(args.cwd)
    if not project_dir:
        print(f"{_c(RED, '❌ No project memory found.')}")
        return 2

    path: Optional[Path] = None
    if getattr(args, "path", None):
        path = Path(args.path)
    elif getattr(args, "session_id", None):
        path = find_session_file(project_dir, args.session_id)
    else:
        latest = load_latest_session(project_dir)
        if latest and latest.lastSessionId:
            path = find_session_file(project_dir, latest.lastSessionId)

    if not path or not path.exists():
        print(f"{_c(RED, '❌ Session not found.')}")
        return 2

    entry = load_session(path)
    if not entry:
        print(f"{_c(RED, '❌ Session file could not be parsed:')} {path}")
        return 2

    needs, reasons = session_needs_compaction(entry)
    if needs:
        print(f"{_c(YELLOW, '⚠️  compaction recommended:')} {'; '.join(reasons)}")
        return 1
    print(f"{_c(GREEN, '✅ within limits')}")
    return 0


def _resolve_stack_sessions(project_dir, args) -> Optional[list]:
    """Build the ref list to layer from --stack NAME and/or positional sids.

    `--stack NAME` becomes an `@NAME` reference so nested/global stacks resolve
    uniformly; positional sids/refs are layered on top.
    """
    refs: list = []
    stack_name = getattr(args, "stack", None)
    if stack_name:
        refs.append("@" + stack_name)
    refs.extend(getattr(args, "sids", []) or [])
    return refs


def cmd_session_list(args: argparse.Namespace) -> int:
    """List sessions (IDs, summary, status) for discovery/referencing."""
    base = find_project_dir(args.cwd)

    targets: list = []
    if getattr(args, "all_repos", False):
        if MEMORY_ROOT.exists():
            targets = [d for d in sorted(MEMORY_ROOT.iterdir())
                       if d.is_dir() and d.name != "_template"]
    elif getattr(args, "repo", None):
        found = find_project_dir_by_name(args.repo)
        if not found:
            print(f"{_c(RED, '❌ Unknown repo')} '{args.repo}'")
            return 2
        targets = [found]
    else:
        if not base:
            print(f"{_c(YELLOW, '⚠️  No project memory for this directory.')} "
                  f"Use --repo NAME or --all-repos.")
            return 2
        targets = [base]

    any_printed = False
    for project_dir in targets:
        sessions = list_sessions(project_dir)
        if not sessions:
            continue
        any_printed = True
        cross = project_dir != base
        print(f"\n{_c(BOLD + CYAN, '📂 ' + project_dir.name)}"
              + (f"  {_c(DIM, '(reference as ' + project_dir.name + '/<id>)')}" if cross else ""))
        for path, entry in sessions:
            folder = path.parent.name
            updated = (entry.lastUpdatedAt or entry.startedAt or "")[:10]
            ref = f"{project_dir.name}/{entry.sessionId}" if cross else entry.sessionId
            summary = entry.summary or "(no summary)"
            print(f"  {_c(BOLD, ref)}  {_c(DIM, f'[{entry.status}] {updated} · {folder}')}")
            print(f"      {summary}")
    if not any_printed:
        print(f"{_c(DIM, 'No sessions found.')}")
    return 0


def cmd_session_stack(args: argparse.Namespace) -> int:
    """Manage and assemble named layer-stacks (chained lists of sessions)."""
    project_dir = find_project_dir(args.cwd) or GLOBAL_DIR
    is_global = getattr(args, "global_", False)
    catalog_dir = GLOBAL_DIR if is_global else project_dir

    action = getattr(args, "stack_action", None)

    if action == "list":
        printed = False
        proj_stacks = load_stacks(project_dir)
        if proj_stacks.stacks and project_dir != GLOBAL_DIR:
            print(f"{_c(BOLD + CYAN, f'🧱 Stacks in {project_dir.name}:')}")
            for s in proj_stacks.stacks:
                desc = f" — {s.description}" if s.description else ""
                print(f"  {_c(BOLD, s.name)} ({len(s.sessions)} layers){desc}")
                print(f"    {_c(DIM, ' → '.join(s.sessions) or '(empty)')}")
            printed = True
        global_stacks = load_global_stacks()
        if global_stacks.stacks:
            print(f"{_c(BOLD + CYAN, '🌍 Global (cross-repo) stacks:')}")
            for s in global_stacks.stacks:
                desc = f" — {s.description}" if s.description else ""
                print(f"  {_c(BOLD, s.name)} ({len(s.sessions)} layers){desc}")
                print(f"    {_c(DIM, ' → '.join(s.sessions) or '(empty)')}")
            printed = True
        if not printed:
            print(f"{_c(DIM, 'No stacks defined. Create one: copilot-memory session stack save <name> <ref...>')}")
        return 0

    if action == "save":
        # Warn (don't block) on refs that don't currently resolve — this catches
        # typos while still allowing forward references to not-yet-created work.
        bad = unresolved_stack_refs(project_dir, args.sids)
        if bad:
            print(f"{_c(YELLOW, '⚠️  Unresolved ref(s) in stack (saved anyway):')} {', '.join(bad)}")
        stack = upsert_stack(project_dir, args.name, args.sids, now_iso(),
                             description=getattr(args, "description", "") or "",
                             append=getattr(args, "append", False),
                             catalog_dir=catalog_dir)
        verb = "Updated" if getattr(args, "append", False) else "Saved"
        where = " (global)" if is_global else ""
        print(f"{_c(GREEN, f'✅ {verb} stack')} '{stack.name}'{where} ({len(stack.sessions)} layers)")
        print(f"  {_c(DIM, ' → '.join(stack.sessions))}")
        return 0

    if action == "rm":
        try:
            updated = remove_from_stack(project_dir, args.name,
                                        getattr(args, "sids", None), now_iso(),
                                        catalog_dir=catalog_dir)
        except KeyError:
            print(f"{_c(RED, '❌ No stack named')} '{args.name}'"
                  + (" (global)" if is_global else ""))
            return 2
        if updated is None:
            print(f"{_c(GREEN, '✅ Deleted stack')} '{args.name}'")
        else:
            print(f"{_c(GREEN, '✅ Updated stack')} '{updated.name}' ({len(updated.sessions)} layers)")
        return 0

    if action == "show":
        refs = _resolve_stack_sessions(project_dir, args)
        if not refs:
            print(f"{_c(RED, '❌ Nothing to layer. Pass --stack NAME and/or session refs.')}")
            return 2
        try:
            rendered, structured = assemble_stack(project_dir, refs)
        except ValueError as e:
            print(f"{_c(RED, '❌')} {e}")
            return 2
        if getattr(args, "json", False):
            print(json.dumps(structured, indent=2, ensure_ascii=False))
        else:
            print(rendered)
        return 0

    if action == "apply":
        refs = _resolve_stack_sessions(project_dir, args)
        if not refs:
            print(f"{_c(RED, '❌ Nothing to layer. Pass --stack NAME and/or session refs.')}")
            return 2
        new_sid = getattr(args, "new_id", None) or str(uuid.uuid4())
        try:
            merged, path = apply_stack(
                project_dir, refs, new_session_id=new_sid,
                now_iso_str=now_iso(), into_name=getattr(args, "into", None),
            )
        except ValueError as e:
            print(f"{_c(RED, '❌')} {e}")
            return 2
        print(f"{_c(GREEN, '✅ Applied stack →')} {path}")
        print(f"  sessionId: {merged.sessionId}")
        print(f"  layers: {', '.join(merged.parents)}")
        return 0

    if action == "refresh":
        sid = getattr(args, "session_id", None)
        path = find_session_file(project_dir, sid) if sid else None
        if path is None:
            print(f"{_c(RED, '❌ Unknown session')} '{sid}'")
            return 2
        merged = load_session(path)
        if merged is None:
            print(f"{_c(RED, '❌ Could not load session')} '{sid}'")
            return 2
        stale = stack_is_stale(project_dir, merged)
        if stale is None:
            print(f"{_c(YELLOW, '⚠️  No layer fingerprint on this session')} "
                  "(applied before auto-refresh existed) — re-apply the stack to enable staleness checks.")
            return 2
        if not stale:
            print(f"{_c(GREEN, '✅ Stack is fresh')} — all {len(merged.sourceVersions)} layer(s) unchanged since apply.")
            return 0
        # Stale: --check only reports (exit 1); otherwise rebuild in place.
        if getattr(args, "check", False):
            print(f"{_c(YELLOW, f'⚠️  Stack stale — {len(stale)} layer(s) updated since apply:')}")
            print(f"    {_c(DIM, ', '.join(stale))}")
            return 1
        rebuilt, new_path, changed = refresh_stack(
            project_dir, merged, now_iso(),
            into_name=getattr(args, "into", None),
        )
        print(f"{_c(GREEN, f'🔄 Refreshed stack — rebuilt from {len(changed)} updated layer(s):')}")
        print(f"    {_c(DIM, ', '.join(changed))}")
        print(f"  sessionId: {rebuilt.sessionId} → {new_path}")
        return 0

    print(f"{_c(YELLOW, 'Specify a stack action: list | save | rm | show | apply | refresh')}")
    return 2


def cmd_init(args: argparse.Namespace) -> int:
    """Create project memory for the current directory."""
    existing = find_project_dir(args.cwd)
    if existing:
        print(f"{_c(GREEN, '✅ Project memory already exists:')} {existing}")
        return 0

    project_dir = ensure_project_dir(args.cwd)

    # Copy template files
    for fname in EXPECTED_FILES:
        fpath = project_dir / fname
        if not fpath.exists():
            template = TEMPLATE_DIR / fname
            if template.exists():
                data = _read_yaml(template)
            else:
                data = {}
            data["schema_version"] = 1
            _write_yaml(fpath, data)

    # Create sessions directory
    (project_dir / "sessions" / "_default").mkdir(parents=True, exist_ok=True)
    (project_dir / "snippets").mkdir(exist_ok=True)

    # Initialize latest.json
    _write_json(project_dir / "sessions" / "latest.json", {
        "lastSessionId": "",
        "lastUpdatedAt": now_iso(),
        "activeSession": None,
    })

    print(f"\n{_c(GREEN + BOLD, '✅ Project memory created:')}")
    print(f"  📂 {project_dir}")
    print(f"  Files: {', '.join(EXPECTED_FILES)}")
    print(f"  Sessions: sessions/_default/")
    print(f"\n  Type {_c(CYAN, ':status')} in Copilot to load it.\n")
    return 0


def cmd_schema_fix(args: argparse.Namespace) -> int:
    """Add schema_version to all YAML files that are missing it."""
    target = args.cwd or str(MEMORY_ROOT)
    root = Path(target)
    if not root.exists():
        print(f"{_c(RED, '❌ Path not found:')} {root}")
        return 1

    fixed = 0
    for yml_path in root.rglob("*.yml"):
        data = _read_yaml(yml_path)
        if data and "schema_version" not in data:
            data["schema_version"] = 1
            _write_yaml(yml_path, data)
            rel = yml_path.relative_to(root)
            print(f"  {_c(GREEN, '✅')} Added schema_version: {rel}")
            fixed += 1

    if fixed == 0:
        print(f"{_c(GREEN, '✅ All YAML files already have schema_version.')}")
    else:
        print(f"\n{_c(GREEN, f'✅ Fixed {fixed} file(s).')}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export project memory for team sharing."""
    project_dir = find_project_dir(args.cwd)
    if not project_dir:
        print(f"{_c(RED, '❌ No project memory found.')}")
        return 1

    context = load_context(project_dir)
    rules = load_rules(project_dir)
    prefs = load_prefs(project_dir)

    lines = [
        "<!-- Auto-exported by copilot-project-memory. Do not edit manually. -->",
        "",
        f"# {context.name or 'Project'} — Copilot Instructions",
        "",
    ]

    # Context
    if context.description:
        lines.append(f"## Project\n{context.description}\n")
    if context.stack:
        lines.append(f"## Tech Stack\n{', '.join(context.stack)}\n")
    if context.key_files:
        lines.append("## Key Files")
        for f in context.key_files:
            lines.append(f"- `{f}`")
        lines.append("")

    # Rules
    shared_rules = [r for r in rules.rules if r.share]
    if shared_rules:
        donts = [r for r in shared_rules if r.type == "dont"]
        dos = [r for r in shared_rules if r.type == "do"]

        if donts:
            lines.append("## Don'ts")
            for r in donts:
                lines.append(f"- {r.description}")
            lines.append("")

        if dos:
            lines.append("## Do's")
            for r in dos:
                lines.append(f"- {r.description}")
            lines.append("")

    output = "\n".join(lines)

    if args.target == "team":
        # Write to .github/copilot-instructions.md
        work_dir = args.cwd or os.getcwd()
        git_root = None
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, cwd=work_dir,
            )
            if result.returncode == 0:
                git_root = result.stdout.strip()
        except Exception:
            pass

        if git_root:
            out_dir = Path(git_root) / ".github" / "instructions"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "project-memory.instructions.md"
            out_path.write_text(output, encoding="utf-8")
            print(f"{_c(GREEN, '✅ Exported to:')} {out_path}")
        else:
            print(output)
    else:
        print(output)

    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _add_cwd(p: argparse.ArgumentParser) -> None:
    """Add --cwd flag to a subparser."""
    p.add_argument("--cwd", help="Working directory override", default=None)


def main():
    parser = argparse.ArgumentParser(
        prog="copilot-memory",
        description="Safety-net CLI for Copilot Project Memory — handles complex ops deterministically.",
    )
    parser.add_argument("--version", action="version", version="copilot-memory 0.1.0")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # status
    p_status = sub.add_parser("status", help="Show project memory health overview")
    _add_cwd(p_status)

    # verify
    p_verify = sub.add_parser("verify", help="Check integrity of memory files")
    p_verify.add_argument("--fix", action="store_true", help="Attempt to repair issues")
    _add_cwd(p_verify)

    # compact
    p_compact = sub.add_parser("compact", help="Enforce storage caps and prune stale data")
    _add_cwd(p_compact)

    # init
    p_init = sub.add_parser("init", help="Create project memory for current directory")
    _add_cwd(p_init)

    # schema-fix
    p_schema = sub.add_parser("schema-fix", help="Add schema_version to all YAML files")
    _add_cwd(p_schema)

    # export
    p_export = sub.add_parser("export", help="Export memory for team sharing")
    p_export.add_argument("target", nargs="?", default="stdout",
                          choices=["team", "stdout"],
                          help="Export target (default: stdout)")
    _add_cwd(p_export)

    # session (group)
    p_session = sub.add_parser("session", help="Session-level helpers")
    session_sub = p_session.add_subparsers(dest="session_command",
                                           help="Session subcommands")

    p_check = session_sub.add_parser(
        "check-size",
        help="Exit 1 if a session crosses compaction thresholds (else 0)",
    )
    p_check.add_argument("--path", help="Explicit path to a session JSON file")
    p_check.add_argument("--session-id", dest="session_id",
                         help="Look up session by ID (searches sessions/**)")
    _add_cwd(p_check)

    p_list = session_sub.add_parser(
        "list",
        help="List sessions (IDs, summary, status) for discovery/referencing",
    )
    p_list.add_argument("--repo", help="List sessions in another repo by name")
    p_list.add_argument("--all-repos", dest="all_repos", action="store_true",
                        help="List sessions across every repo's memory")
    _add_cwd(p_list)

    p_arch = session_sub.add_parser(
        "archive",
        help="Gzip closed sessions older than N days (default: 7)",
    )
    p_arch.add_argument("--older-than-days", dest="older_than_days",
                        type=int, default=7,
                        help="Only archive closed sessions this many days old (default: 7)")
    _add_cwd(p_arch)

    p_merge = session_sub.add_parser(
        "merge",
        help="Merge N existing sessions into a new session (inherits their context)",
    )
    p_merge.add_argument("sids", nargs="+", help="Parent session IDs to merge")
    p_merge.add_argument("--into", help="Target named-session folder (default: _default)")
    p_merge.add_argument("--new-id", dest="new_id",
                         help="Explicit session ID for the merged session (default: random UUID)")
    p_merge.add_argument("--dry-run", dest="dry_run", action="store_true",
                         help="Preview merge without writing")
    _add_cwd(p_merge)

    # --- session stack (named, ordered chains layered for rich context) ---
    p_stack = session_sub.add_parser(
        "stack",
        help="Layer sessions into rich context via named chains (pick & choose)",
    )
    stack_sub = p_stack.add_subparsers(dest="stack_action", help="Stack actions")

    ps_list = stack_sub.add_parser("list", help="List all named stacks")
    _add_cwd(ps_list)

    ps_save = stack_sub.add_parser(
        "save", help="Create/replace a named stack (ordered base→top)")
    ps_save.add_argument("name", help="Stack name (e.g. common, BMS)")
    ps_save.add_argument("sids", nargs="+",
                         help="Refs in layer order (base first): sessionId, @stack, repo/sessionId, repo/@stack")
    ps_save.add_argument("--append", action="store_true",
                         help="Append to the existing chain instead of replacing")
    ps_save.add_argument("--description", help="Optional description")
    ps_save.add_argument("--global", dest="global_", action="store_true",
                         help="Store in the global cross-repo catalog (_global)")
    _add_cwd(ps_save)

    ps_rm = stack_sub.add_parser(
        "rm", help="Remove sessions from a stack, or delete the whole stack")
    ps_rm.add_argument("name", help="Stack name")
    ps_rm.add_argument("sids", nargs="*",
                       help="Refs to remove (omit to delete the stack)")
    ps_rm.add_argument("--global", dest="global_", action="store_true",
                       help="Target the global cross-repo catalog (_global)")
    _add_cwd(ps_rm)

    ps_show = stack_sub.add_parser(
        "show", help="Assemble & print the layered context for a stack and/or refs")
    ps_show.add_argument("--stack", help="Named stack to layer (project or global)")
    ps_show.add_argument("sids", nargs="*",
                         help="Extra refs to layer on top: sessionId, @stack, repo/sessionId, repo/@stack")
    ps_show.add_argument("--json", action="store_true", help="Emit structured JSON")
    _add_cwd(ps_show)

    ps_apply = stack_sub.add_parser(
        "apply", help="Materialize a stack (incl. cross-repo) as a new merged session")
    ps_apply.add_argument("--stack", help="Named stack to layer (project or global)")
    ps_apply.add_argument("sids", nargs="*", help="Extra refs to layer on top")
    ps_apply.add_argument("--into", help="Target named-session folder (default: _default)")
    ps_apply.add_argument("--new-id", dest="new_id", help="Explicit merged session ID")
    _add_cwd(ps_apply)

    ps_refresh = stack_sub.add_parser(
        "refresh",
        help="Rebuild a materialized stack if any source layer changed since apply")
    ps_refresh.add_argument("--session", dest="session_id", required=True,
                            help="The materialized (applied) merged session ID to check/refresh")
    ps_refresh.add_argument("--check", action="store_true",
                            help="Only report staleness (exit 0 fresh, 1 stale); don't rebuild")
    ps_refresh.add_argument("--into", help="Target named-session folder (default: _default)")
    _add_cwd(ps_refresh)

    args = parser.parse_args()

    if args.command == "status":
        sys.exit(cmd_status(args))
    elif args.command == "verify":
        sys.exit(cmd_verify(args))
    elif args.command == "compact":
        sys.exit(cmd_compact(args))
    elif args.command == "init":
        sys.exit(cmd_init(args))
    elif args.command == "schema-fix":
        sys.exit(cmd_schema_fix(args))
    elif args.command == "export":
        sys.exit(cmd_export(args))
    elif args.command == "session":
        if getattr(args, "session_command", None) == "list":
            sys.exit(cmd_session_list(args))
        if getattr(args, "session_command", None) == "check-size":
            sys.exit(cmd_session_check_size(args))
        if getattr(args, "session_command", None) == "archive":
            sys.exit(cmd_session_archive(args))
        if getattr(args, "session_command", None) == "merge":
            sys.exit(cmd_session_merge(args))
        if getattr(args, "session_command", None) == "stack":
            sys.exit(cmd_session_stack(args))
        parser.parse_args(["session", "--help"])
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
