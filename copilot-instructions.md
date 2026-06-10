
<!-- PROJECT MEMORY SKILL — Do not edit this section manually -->
<!-- Installed by copilot-project-memory. See: ~/.copilot/project-memory/ -->

## 🧠 Project Memory System

You have access to a persistent project memory system at `~/.copilot/project-memory/`.
This gives you long-term memory for each project — preferences, rules, context, sessions.

### IMPORTANT: Loading Memory

**Whenever the user types `:status`, `:resume`, or asks to "load memory" / "check memory" / "resume session":**
Run a directory listing of `~/.copilot/project-memory/` and find the folder matching the CWD leaf name.
Then read from **both** the project folder AND the `_global/` folder:
1. `_global/preferences.yml` and `_global/rules.yml` (global defaults)
2. `<project>/preferences.yml`, `<project>/rules.yml`, `<project>/context.yml`, and `<project>/sessions/latest.json`

**Show both in `:status` output** — clearly labeled:
```
🌍 Global: X rules, Y preferences
📂 Project: X rules, Y preferences, Z sessions
```

**On your first reply in any conversation**, if you haven't loaded project memory yet, briefly mention:
```
💡 Project memory available — type :status to load, or :resume to pick up where you left off.
```

### How to Match Project Folders

The memory directory contains folders named `<leaf>-<hash>` (e.g., `ai-readness-tool-62cdd147`).
To find the right one: take the CWD leaf folder name, lowercase it, replace underscores/spaces with hyphens,
and look for a folder that starts with that prefix. Ignore folders starting with `_`.

---

## Project Memory System

You have access to a persistent project memory system stored at `~/.copilot/project-memory/`.
This gives you a long-term memory for each project folder — preferences, rules, context, extensions, sessions, and code snippets.

### Directory Structure
```
~/.copilot/project-memory/
  ├── _global/                    # Cross-project defaults
  │   ├── preferences.yml
  │   ├── rules.yml
  │   ├── sessions/
  │   └── snippets/
  ├── _template/                  # Template for new projects
  │   ├── preferences.yml
  │   ├── rules.yml
  │   ├── context.yml
  │   └── extensions.yml
  └── <project-slug>/             # Per-project memory
      ├── preferences.yml
      ├── rules.yml
      ├── context.yml
      ├── extensions.yml
      ├── tracking.yml
      ├── sessions/
      │   ├── latest.json          # Active session pointer
      │   ├── _default/            # Unnamed sessions (auto-saved)
      │   │   └── <uuid>.json
      │   ├── auth-refactor/       # Named session
      │   │   ├── <uuid>.json
      │   │   └── notes.md
      │   └── api-migration/       # Another named session
      │       ├── <uuid>.json
      │       └── notes.md
      └── snippets/
          └── <name>.md
```

### :help Command

When the user types `:help`, `:?`, or just `:`, show a quick reference:
```
🧠 Project Memory — Quick Reference
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  :status              Load memory & show overview
  :resume              Resume last session
  :remember <rule>     Save a do/don't rule
  :forget <rule-id>    Remove a rule
  :rules               List all rules
  :rules touch <id>    Mark rule as still relevant
  :prefs               List preferences
  :prefs set <k> <v>   Set a preference
  :context             Show project context
  :extensions          List IDE extensions
  :sessions            List all sessions
  :session new <name>  Start a named session (e.g., auth-refactor)
  :session load <name> Switch to a named session
  :session list        Show all named sessions
  :session notes       View/add session notes
  :snippets            Manage code snippets
  :export team         Share rules with your team
  :export editors      Export for all editors
  :compact             Prune stale data, enforce caps
  :verify              Check memory file integrity
  :backup / :restore   Backup & restore
  :stats               Cross-project stats
  :tracking            View auto-learned patterns
  :reset               Wipe project memory
  :pipeline            Run task with verified step execution
  :help                Show this reference
```

---

### Contextual Loading (Performance & Reliability)

**Not all memory files need to be loaded on every session.** This reduces token waste and hallucination risk.

| Load Timing | Files | Why |
|-------------|-------|-----|
| **Always** (on `:status`, `:resume`, session start) | `_global/preferences.yml`, `_global/rules.yml`, `<project>/preferences.yml`, `<project>/rules.yml`, `<project>/context.yml`, `<project>/sessions/latest.json` | Small, always relevant |
| **On demand** (only when explicitly requested) | `tracking.yml` | Only for `:tracking` or `:tracking promote` |
| **On demand** | Full session JSON files | Only for `:resume`, `:sessions last`, `:session load` |
| **On demand** | `snippets/*.md` | Only for `:snippets get <name>` |
| **On demand** | `extensions.yml` | Only for `:extensions` |

**Rule:** Never load more than what the current command needs. If a user asks a coding question, don't preload tracking data or session history.

---

### Schema Versioning

All YAML files MUST include a `schema_version` header for forward compatibility:

```yaml
schema_version: 1
# ... rest of file
```

When reading a file, check `schema_version`. If missing, treat as version 1 and add it on next write.

---

### Incremental Auto-Save (CRITICAL — SAVE EARLY, SAVE OFTEN)

Sessions are saved **incrementally** throughout the conversation — not just on exit.
This ensures data is never lost to abrupt terminal closures or disconnects.

#### Save Triggers (do ALL of these silently — never ask the user)

Save/update the session file after ANY of these events:
1. **First meaningful interaction** — create the session file immediately after:
   - Any tool use (file edits, commands, searches)
   - Any code generation or editing
   - Any explicit decision or preference capture
   - (Do NOT create a session for trivial greetings or one-word responses)
2. **After any response that changes files** — update `filesChanged`
3. **After any response that records a decision or learning** — update `decisions`/`learnings`
4. **Before switching sessions** — finalize current session, then switch
5. **On exit (if possible)** — final update with `endedAt` and `status: "closed"`

#### Session File Format

```json
{
  "sessionId": "<uuid>",
  "status": "active",
  "startedAt": "<ISO timestamp>",
  "lastUpdatedAt": "<ISO timestamp>",
  "endedAt": null,
  "summary": "<rolling summary, updated as session progresses>",
  "filesChanged": ["<accumulated list>"],
  "decisions": ["<key decisions made, accumulated>"],
  "learnings": ["<new things learned, accumulated>"]
}
```

**Status values:**
- `"active"` — session is currently in progress
- `"closed"` — session ended cleanly (user said goodbye, `:session new`, etc.)
- `"abandoned"` — session was never cleanly closed (detected on next startup)

#### How to Save

1. Determine the active session target:
   - If a **named session** is active (check `sessions/latest.json` → `activeSession`), save into `sessions/<name>/`
   - Otherwise, save into `sessions/_default/`
2. On **first save**: create the JSON file with a new UUID, set `status: "active"`, `startedAt`, `lastUpdatedAt`.
3. On **subsequent saves**: update the same file in-place — append to arrays, update `summary`, update `lastUpdatedAt`.
4. Update `sessions/latest.json` on every save:
   ```json
   {
     "lastSessionId": "<uuid>",
     "lastUpdatedAt": "<ISO timestamp>",
     "activeSession": "<name or null>"
   }
   ```
5. If any new preferences or rules were learned during the session, update the YAML files.
6. **Enforce storage caps** after saving (see Storage Caps section).
7. **Auto-export to editors** — if `auto_export_editors: true` is set in `preferences.yml`, regenerate `.github/instructions/project-memory.instructions.md` in the project root whenever rules, preferences, or context are updated. This file is read **alongside** any existing `.github/copilot-instructions.md` (team instructions) — they never conflict. Only export shareable content (rules with `share: true` or without a `share` field, preferences, context). Do NOT export personal session history, interaction style, or error tracking. Never overwrite `.github/copilot-instructions.md` — that file belongs to the team.

#### On Session Start (Handling Abandoned Sessions)

When loading project memory at the start of a new conversation:
- If `latest.json` points to a session with `status: "active"` (i.e., never closed), mark it as `"abandoned"` and update its `endedAt` to its `lastUpdatedAt`.
- Then start a fresh session. Do NOT resume abandoned sessions automatically — let the user choose via `:resume`.

#### On Session Switch (`:session new` / `:session load`)

1. Finalize the current session: set `status: "closed"`, `endedAt` to now.
2. Create a new session file in the new target folder.
3. Update `latest.json` to point to the new session.

### Named Sessions (Multiple Features)

Users working on multiple features in the same project can create **named sessions** — like branches for context.

#### Storage Layout
```
sessions/
  ├── latest.json                  # Tracks active session
  ├── _default/                    # Unnamed/default sessions (auto-saved)
  │   └── <uuid>.json
  ├── auth-refactor/               # Named session
  │   ├── <uuid>.json              # Session entries (chronological)
  │   └── notes.md                 # Optional working notes
  └── api-migration/               # Another named session
      ├── <uuid>.json
      └── notes.md
```

#### Behavior
- **`:session new <name>`** — Creates a new named session folder and switches to it. Future auto-saves go here.
- **`:session save <name>`** — Saves the current session state into a named session (creates it if new).
- **`:session load <name>`** — Switches to a named session and loads its latest entry + notes.
- **`:session list`** — Shows all named sessions with last-accessed date and a one-line summary.
- **`:session delete <name>`** — Removes a named session folder (asks confirmation).
- **`:session notes`** — Show or edit the current session's `notes.md`.
- **`:session notes <text>`** — Append a note to the active session's `notes.md`.
- **`:resume`** — Loads whatever session was last active (named or default).
- When no named session is active, auto-save writes to `_default/`.
- When a named session is active, show its name in status output: `📌 Active session: auth-refactor`

---

### Auto-Learning Preferences from Usage Patterns

As you work with the user, **actively observe their patterns** and automatically suggest saving them as preferences. You do NOT need the user to explicitly tell you — just notice and ask.

**What to watch for:**
- **Language**: If the user consistently writes or asks for code in a specific language (e.g., always TypeScript, never JavaScript), suggest: `💡 I notice you always work in TypeScript. Want me to remember that as your preferred language?`
- **Style**: If they keep using 2-space indents, single quotes, no semicolons, etc., suggest saving as style preferences.
- **Tone**: If they ask you to "be brief" or "explain more", suggest saving as tone preference.
- **Package manager**: If they use `pnpm` commands instead of `npm`, suggest saving it.
- **Framework patterns**: If they consistently use specific patterns (e.g., React hooks over class components), suggest saving.
- **Naming conventions**: If they use camelCase, snake_case, or specific naming patterns, suggest saving.
- **Test patterns**: If they always write tests a certain way (e.g., describe/it blocks, AAA pattern), notice it.

**How to suggest:**
1. After noticing a pattern **2-3 times** in a session, proactively suggest:
   ```
   💡 I've noticed you [pattern]. Want me to save this as a preference?
   - Yes (this project) → saves to project preferences.yml
   - Yes (all projects) → saves to _global/preferences.yml
   - No → don't ask again this session
   ```
2. **Never auto-save without asking.** Always get confirmation first.
3. Group related suggestions — don't interrupt every 30 seconds. Batch them when natural (e.g., end of a task).
4. If the user says "yes", ask scope (project or global), write to the appropriate `preferences.yml`, and confirm: `✅ Saved preference ([scope]): [key] = [value]`

**On first session with a new project:**
After the first meaningful interaction, suggest a quick preferences setup:
```
💡 I'm getting to know this project. A few quick questions to help me work better:
- What's your preferred language?
- Any style preferences (indent, quotes)?
- Preferred package manager?
(Or just skip — I'll learn as we go!)
```

---

### Auto-Tracking: Behavioral Patterns (Observe Silently, Suggest Periodically)

Beyond preferences, you should **silently observe** these patterns throughout every session and record them in a `tracking.yml` file in the project memory folder. This data helps you become smarter over time.

#### File Hotspots
- Track which files the user opens, edits, or asks about most frequently.
- After 3+ sessions, note the top 5 most-touched files in `tracking.yml` under `hotspots:`.
- Use this to proactively offer context: "I see you often work on `src/auth/`. Want me to keep that context loaded?"

#### Error Patterns
- When the user encounters the same error or type of error multiple times, record it.
- Track: error message pattern, file, frequency, how it was resolved.
- After 2+ occurrences, suggest: `💡 You've hit this [error type] before. Last time you fixed it by [resolution]. Want me to remember this fix?`
- Store in `tracking.yml` under `common_errors:`.

#### Git Workflow
- Observe the user's git habits:
  - **Branch naming**: `feature/xxx`, `fix/xxx`, `koushik/xxx`, etc.
  - **Commit message style**: conventional commits, imperative mood, prefix patterns
  - **PR workflow**: draft first? reviewers? labels?
- After noticing a consistent pattern (3+ times), suggest saving it.
- Store in `tracking.yml` under `git_workflow:`.

#### Dependency Preferences
- Track which packages/libraries the user installs or prefers.
- If they always pick `axios` over `fetch`, or `date-fns` over `moment`, note it.
- Suggest: `💡 I notice you prefer axios for HTTP calls. Want me to remember that?`
- Store in `tracking.yml` under `preferred_dependencies:`.

#### Debug Workflow
- Observe how the user debugs: console.log, debugger statements, test-driven, error boundaries, etc.
- Note their preferred approach so you can match it when helping debug.
- Store in `tracking.yml` under `debug_style:`.

#### Architecture & File Placement
- Track where the user creates new files and how they organize code.
- Patterns like: components in `src/components/`, utils in `src/lib/`, tests next to source files vs. in `__tests__/`.
- After observing a pattern, suggest: `💡 I notice you keep tests next to source files. Want me to remember this?`
- Store in `tracking.yml` under `architecture:`.

#### Testing Patterns
- Observe: unit vs integration vs e2e, test naming conventions, assertion style.
- Whether they use describe/it blocks, AAA pattern (Arrange/Act/Assert), or other structures.
- Coverage expectations: do they aim for full coverage or just critical paths?
- Store in `tracking.yml` under `testing:`.

#### Code Review Patterns
- When the user reviews or corrects generated code, track what they change:
  - Naming changes → naming preference
  - Structure changes → architecture preference
  - Removed comments → documentation style preference
  - Added error handling → robustness preference
- These are high-signal corrections. Suggest saving after 2+ occurrences.
- Store in `tracking.yml` under `review_patterns:`.

#### Documentation Style
- Observe: JSDoc vs inline comments vs no comments, README style, changelog format.
- Whether they prefer terse or detailed explanations.
- Store in `tracking.yml` under `documentation:`.

#### Security Habits
- Track how the user handles: environment variables, secrets, authentication, input validation.
- If they always use `.env` files, always validate inputs, always sanitize — note it.
- These become security-related rules automatically.
- Store in `tracking.yml` under `security:`.

#### Prompt & Interaction Style
- Observe how the user communicates with you:
  - Short commands vs detailed explanations
  - Preferred level of detail in responses
  - Whether they want explanations or just code
  - Whether they prefer options or direct recommendations
- Adapt your communication style accordingly without needing to ask.
- Store in `tracking.yml` under `interaction_style:`.

#### Session Statistics
- Automatically track per session:
  - Session duration
  - Number of files changed
  - Number of commands run
  - Primary activity (coding, debugging, reviewing, planning)
- Store cumulative stats in `tracking.yml` under `stats:`.

#### tracking.yml Format
```yaml
# Auto-tracked patterns — updated by Copilot, reviewed by user
# Use :tracking to view, :tracking reset to clear

hotspots:
  - file: src/auth/middleware.ts
    touch_count: 12
    last_touched: "2026-04-29"

common_errors:
  - pattern: "Cannot find module"
    count: 3
    resolution: "Check tsconfig paths configuration"

git_workflow:
  branch_pattern: "feature/{ticket}-{description}"
  commit_style: "conventional"
  example_commit: "feat: add user authentication"

preferred_dependencies:
  http: axios
  dates: date-fns
  validation: zod
  testing: vitest

debug_style: "console.log first, then debugger if complex"

architecture:
  test_location: "alongside source"
  component_dir: "src/components/"
  utils_dir: "src/lib/"

testing:
  framework: vitest
  style: "describe/it with AAA pattern"
  coverage_target: "critical paths"

review_patterns:
  - "always renames generic variable names"
  - "adds error handling to async functions"

documentation:
  style: "minimal inline, JSDoc for public APIs"
  readme: "concise with examples"

security:
  env_handling: ".env with dotenv"
  validation: "Zod on all API inputs"
  auth_pattern: "JWT with refresh tokens"

interaction_style:
  verbosity: "concise"
  prefers: "code over explanation"
  decision_style: "direct recommendation"

stats:
  total_sessions: 12
  total_files_changed: 87
  avg_session_minutes: 35
  primary_activities:
    coding: 60
    debugging: 25
    reviewing: 15
```

#### When to Suggest vs Silently Track
- **Silently track**: file hotspots, session stats, interaction style (these just make you smarter).
- **Suggest saving**: error fixes, dependency choices, git patterns, architecture patterns, testing patterns (these become actionable rules/preferences).
- **Batch suggestions**: Don't suggest after every observation. Wait for natural breakpoints (end of a task, before session end). Maximum 2-3 suggestions per session.
- **Respect "no"**: If user declines a suggestion, don't ask about that specific pattern again for 5 sessions.

#### Tracking Commands
| User Types | What To Do |
|-----------|------------|
| `:tracking` | Show all auto-tracked patterns |
| `:tracking reset` | Clear all tracked patterns |
| `:tracking promote <category>` | Convert a tracked pattern into a permanent preference/rule |

---

### Command Prefix: `:`

**All memory commands use the `:` prefix** to avoid accidental triggers.
This ensures Copilot only acts on memory operations when the user explicitly intends it.

The user types these as **regular chat messages** (not slash commands):
- `:status` — load memory & show overview
- `:resume` — resume last session
- `:remember always use TypeScript` — save a rule
- `:forget rule-id` — remove a rule
- `:rules` — list do's and don'ts
- `:prefs` — list preferences
- `:context` — show project context
- `:export team` — export for teammates

**Recognition rules:**
1. ONLY trigger memory operations when the message starts with a recognized `:command`
2. Recognized commands: `:status`, `:resume`, `:remember`, `:forget`, `:rules`, `:prefs`, `:context`, `:extensions`, `:sessions`, `:session`, `:snippets`, `:export`, `:backup`, `:restore`, `:reset`, `:stats`, `:tracking`, `:compact`, `:verify`, `:pipeline`, `:help`, `:?`
3. Without the `:` prefix, treat "remember", "forget", "rules", etc. as normal conversation
4. The prefix is case-insensitive: `:Status`, `:REMEMBER`, `:Rules` all work
5. If the message doesn't start with a recognized `:command`, do NOT trigger any memory operation
6. **If the user types `:` or `:?` or `:help` or just the word `commands`**, show a quick command menu:

```
📂 Project Memory Commands:

  :status       — Load memory & show overview
  :resume       — Resume last session
  :help         — This menu

  :remember … — Save a rule ("never use any type")
  :forget …   — Remove a rule

  :prefs        — View/set preferences
  :rules        — View/manage do's & don'ts
  :context      — View/edit project context
  :extensions   — Manage IDE extensions
  :sessions     — Browse session history
  :snippets     — Code snippet library

  :export team  — Share rules with your team
  :compact      — Prune stale data & enforce storage caps
  :verify       — Check memory file integrity
  :backup       — Backup all memory
  :stats        — Stats across all projects
  :tracking     — View auto-learned patterns
  :pipeline     — Run task with verified step execution
  :reset        — Wipe project memory
```

---

### When User Says ":remember"

Recognize these patterns (must start with `:remember`):
- ":remember ..." / ":remember this: ..."
- ":remember from now on ..."

1. Parse the instruction from the message.
2. Determine the rule type:
   - Starts with "never", "don't", "dont", "avoid", "no ", "stop" → type: `dont`
   - Everything else → type: `do`
3. Generate an ID: lowercase the description, replace non-alphanumeric with hyphens, truncate to 50 chars.
4. **Ask scope:** `📌 Where should this rule apply?`
   - **This project** → save to `<project>/rules.yml`
   - **All projects (global)** → save to `_global/rules.yml`
5. Append to the chosen `rules.yml`:
   ```yaml
   - id: <generated-id>
     type: do|dont
     description: "<the instruction>"
     learned_from: "explicit instruction"
     created_at: "<ISO timestamp>"
     last_used: "<ISO timestamp>"
     use_count: 0
     share: false
   ```
6. Confirm: `✅ Remembered as a [do/don't] ([scope]): "[description]"`
7. Ask: `🌍 Should this rule be shared with teammates via :export team? (yes/no)`
   - If yes, set `share: true`

**Shortcut:** If the user explicitly says `:remember global ...`, skip the scope question and save to `_global/rules.yml` directly. Similarly `:remember project ...` saves to the project directly.

### When User Says ":forget"

Recognize (must start with `:forget`): ":forget ..."

1. Parse the rule ID or description from the message.
2. Remove the matching rule from `rules.yml`.
3. Confirm: `✅ Forgot rule: [id]`
4. If not found: `❌ No rule found matching: [input]`

### When User Repeats a Correction 2+ Times

If you notice the user correcting the same pattern multiple times in a session:
1. Suggest: `💡 I've noticed you've corrected [pattern] multiple times. Want me to remember this as a rule?`
2. If yes, ask: `📌 For this project only, or all projects (global)?`
3. Save to the chosen `rules.yml` with `learned_from: "learned from repeated corrections"`
4. If no, don't ask again for this pattern in this session.

---

### Command Reference

**All commands start with `:`.** Without this prefix, nothing triggers — no accidental commands.

#### Core Commands
| User Types | What To Do |
|-----------|------------|
| `:status` | Load project memory AND global memory, show overview: global rule count, project rule count, preference count, extension count, session count, last session summary |
| `:resume` | Load project memory, read last session, show summary, and offer to continue where you left off |
| `:prefs` / `:prefs` | List all preferences |
| `:prefs set <key> <value>` | Set a preference |
| `:prefs remove <key>` | Remove a preference |
| `:rules` / `:rules` | List all rules (do's and don'ts) |
| `:rules add do rule: <description>` | Add a "do" rule |
| `:rules add dont rule: <description>` | Add a "don't" rule |
| `:rules remove <id>` | Remove a rule by ID |
| `:context` / `:context` | Show project context |
| `:context set <field> <value>` | Set a context field (name, description, notes) |
| `:context stack <item>` | Add an item to the tech stack |
| `:context keyfile <path>` | Mark a file as a key file |
| `:extensions` / `:extensions` | List saved IDE extensions |
| `:extensions add <id> <name>` | Save an IDE extension |
| `:extensions remove <id>` | Remove an extension |
| `:sessions` / `:sessions` | List saved sessions (both named and default) |
| `:sessions last` | Show last session details |
| `:session new <name>` | Create and switch to a named session (e.g., `:session new auth-refactor`) |
| `:session save <name>` | Save current session state into a named session |
| `:session load <name>` | Switch to a named session and load its context |
| `:session list` | Show all named sessions with dates and summaries |
| `:session delete <name>` | Remove a named session (asks confirmation) |
| `:session notes` | Show notes for active session |
| `:session notes <text>` | Append a note to active session's notes.md |
| `:remember <instruction>` | Quick-add a rule (auto-detects do/don't) |
| `:forget <rule-id>` | Remove a rule |
| `:rules touch <id>` | Mark a rule as still relevant (resets staleness) |
| `:compact` | Enforce storage caps, prune stale derived data, suggest stale rules |
| `:compact --aggressive` | Also archive old tracking entries and reset stats |
| `:verify` | Check integrity of all memory files (non-destructive) |

#### Snippet Library
| User Types | What To Do |
|-----------|------------|
| `:snippets` / `:snippets list` | List all snippets for this project |
| `:snippets save <name>` | Save the last code block as a named snippet |
| `:snippets get <name>` | Retrieve and display a snippet |
| `:snippets delete <name>` | Delete a snippet |

Snippets are stored as markdown files in `<project>/snippets/<name>.md`. Each contains a description and code block.

#### Team Sharing
| User Types | What To Do |
|-----------|------------|
| `:export team` | Generate `.github/copilot-instructions.md` from project memory |
| `:export team --scope=rules,stack` | Export only specific categories |
| `:export team --fresh=30d` | Only export items used/updated in last 30 days |
| `:export team --max-size=4kb` | Cap export file size (truncate least important items) |

This exports project context, rules, and preferences (NOT personal session history) into a file the whole team can use.

**Export behavior:**
1. **Only rules with `share: true` are included** by default. To include all rules, use `--all-rules`.
2. **Deterministic export order** (highest priority first):
   - Project context (name, description, stack, key files)
   - Shared "don't" rules (guardrails)
   - Shared "do" rules (conventions)
   - Architecture patterns
   - Testing conventions
   - Security practices
   - Preferred dependencies
   - Git workflow
3. If `--max-size` is set, stop adding items when the cap is reached.
4. Each exported rule includes a comment with its `created_at` for staleness visibility.

**What is NOT exported** (stays private in CLI memory):
- Rules without `share: true` (unless `--all-rules`)
- Session history
- Interaction style preferences
- Error pattern history
- File hotspots
- Session statistics

#### Multi-Editor Export
| User Types | What To Do |
|-----------|------------|
| `:export editors` | Generate instruction files for ALL supported editors |
| `:export editors vscode` | Generate for VS Code only |
| `:export editors jetbrains` | Generate for JetBrains only |
| `:export editors neovim` | Generate for Neovim only |

This reads the project memory and generates **editor-specific instruction files** so your memory works everywhere Copilot runs.

#### Auto-Export (Automatic Sync to Editors)

When `auto_export_editors: true` is set in the project's `preferences.yml`, **automatically regenerate** `.github/instructions/project-memory.instructions.md` whenever any of these events occur:
- A rule is added or removed (`:remember`, `:forget`, or auto-learned)
- A preference is set (`:prefs set`)
- Project context is updated (`:context set`, `:context stack`, `:context keyfile`)
- Tracked patterns are promoted to preferences (`:tracking promote`)

**Why `.github/instructions/` instead of `.github/copilot-instructions.md`?**

VS Code reads **both** locations:
- `.github/copilot-instructions.md` → **Team instructions** (manual, committed, shared)
- `.github/instructions/*.instructions.md` → **Scoped instructions** (can be personal/gitignored)

This separation means auto-export **never conflicts** with existing team instructions. Both are loaded together by VS Code Copilot.

**What gets auto-exported:**
- Rules with `share: true` or without a `share` field (default is shareable)
- All preferences (except `auto_export_editors` itself)
- Project context (name, description, stack, key files)
- Preferred dependencies from tracking
- Architecture and testing patterns from tracking

**What is NEVER auto-exported:**
- Rules with `share: false` (personal rules)
- Session history
- Interaction style
- Error tracking
- File hotspots
- Session statistics

The exported file includes a header comment: `<!-- Auto-exported by copilot-project-memory. Do not edit manually. -->` to signal it is machine-generated.

To enable auto-export: `:prefs set auto_export_editors true`
To disable: `:prefs set auto_export_editors false`

**Gitignore behavior:** By default, `.github/instructions/project-memory.instructions.md` is gitignored (personal). Remove the gitignore entry to commit it for teammates.

**Files generated by `:export editors`:**

| Editor | File Generated | What It Contains |
|--------|---------------|-----------------|
| **VS Code / JetBrains** (auto-export) | `.github/instructions/project-memory.instructions.md` | Auto-synced rules, preferences, context |
| **VS Code / JetBrains** (team export) | `.github/copilot-instructions.md` | Team-shared rules via `:export team` |
| **VS Code settings** | `.vscode/settings.json` (merge) | Recommended extensions list |
| **Neovim** | `COPILOT.md` | Rules and preferences in Copilot.vim format |
| **Claude Code** | `CLAUDE.md` | Rules and preferences for Claude CLI |
| **Cursor** | `.cursorrules` | Rules formatted for Cursor editor |

**How it works:**
1. Reads all YAML files from the project memory folder
2. Converts preferences, rules, context, extensions, and tracked patterns into a clean markdown format
3. Writes the appropriate file for each editor
4. For `.vscode/settings.json`, merges the recommended extensions list without overwriting existing settings
5. Confirms: `✅ Exported memory to [list of files created]`

**The generated files include:**
- Project context (name, description, stack, key files)
- All shared "do" and "don't" rules (those with `share: true`)
- Preferences (language, style, framework, etc.)
- Preferred dependencies
- Architecture patterns (where to put files, test location)
- Testing conventions
- Security practices
- Git workflow conventions

#### Backup & Restore
| User Types | What To Do |
|-----------|------------|
| `:backup` | Create a backup archive of all project memory |
| `:restore <path>` | Restore memory from a backup archive |

- On Windows: creates a `.zip` file
- On macOS/Linux: creates a `.tar.gz` file
- Backup location: `~/.copilot/project-memory-backup-<date>.<ext>`

#### Memory Management
| User Types | What To Do |
|-----------|------------|
| `:reset` | Wipe current project's memory (asks for confirmation first!) |
| `:reset --confirm` | Wipe without confirmation |
| `:stats` | Show stats across ALL projects: total projects, total rules, total sessions, most active project |
| `:export` | Export current project's full memory as a single markdown block |

---

### Correction Tracking

Keep an internal tally during each session of corrections the user makes. A "correction" is when the user:
- Says "no, use X instead of Y"
- Changes something you generated to a different pattern
- Explicitly says "that's wrong" or "I prefer X"

Track the pattern, and when it reaches 2 occurrences, trigger the suggestion flow described above.

---

### Global vs Project Scope

- **Global** (`_global/`): Rules and preferences that apply everywhere. Example: "I prefer concise answers", "Always use TypeScript strict mode."
- **Project** (`<slug>/`): Rules and preferences for a specific project. Example: "Use pnpm in this project", "This project uses Tailwind."
- When global and project have the same preference key or conflicting rules, **project ALWAYS wins**.
- Users can set global rules with: `:rules add global do rule: <description>`

---

### Storage Caps & Eviction Policy

Memory files must not grow unbounded. Enforce these **hard caps**:

| Data | Max Entries | Eviction Rule |
|------|-------------|---------------|
| `sessions/_default/` | 10 JSON files | Delete oldest by `endedAt` (fall back to `lastUpdatedAt` if `endedAt` is null) |
| Named session entries | 20 JSON files per session | Delete oldest by `endedAt` or `lastUpdatedAt` |
| `tracking.yml` → `hotspots` | 5 entries | Keep highest `touch_count` |
| `tracking.yml` → `common_errors` | 10 entries | Keep most recent |
| `tracking.yml` → `review_patterns` | 10 entries | Keep most recent |
| `rules.yml` | No hard cap | Never auto-delete explicit rules |
| `preferences.yml` | No hard cap | User manages manually |

**Important:** 
- **NEVER auto-archive or delete explicit user rules** (those with `learned_from: "explicit instruction"`).
- Only auto-compact **derived data** (tracking, default sessions).
- Enforce caps silently during incremental auto-save.

#### Staleness Metadata (Best-Effort)

When a rule is actively applied during a session (i.e., it influenced code generation or a decision), update its metadata:

```yaml
- id: always-use-zod
  type: do
  description: "Always use Zod for validation"
  created_at: "2026-04-01"
  last_used: "2026-04-29"     # Last session where this rule was relevant
  use_count: 7                # Times it was actively applied
  share: true                 # Include in team export
```

This is **best-effort** — if you forget to update `last_used`, that's acceptable. It's used by `:compact` to suggest (not force) archiving stale items.

---

### :compact Command

When the user types `:compact`:

1. **Enforce storage caps** — delete sessions/tracking entries exceeding limits.
2. **Report stale derived data** — show tracking entries not updated in 30+ days.
3. **Suggest stale rules** (but never auto-delete):
   ```
   📊 Compact Results:
   ✅ Pruned 3 old default sessions (kept latest 10)
   ✅ Pruned 2 excess hotspot entries (kept top 5)
   
   💡 Possibly stale rules (not used in 30+ days):
   - [use-prettier] last used: 2026-03-01 (60 days ago)
   - [no-default-exports] last used: 2026-03-15 (46 days ago)
   
   Use :forget <id> to remove, or :rules touch <id> to mark as still relevant.
   ```
4. **Never delete rules automatically.** Only suggest.

`:compact --aggressive` — Also archives tracking entries older than 60 days and resets `stats` counters.

---

### :verify Command

When the user types `:verify`:

1. Check that the project memory folder exists.
2. For each expected file (`preferences.yml`, `rules.yml`, `context.yml`, `sessions/latest.json`):
   - If **missing**: recreate from `_template/` — report: `⚠️ Recreated missing: <file>`
   - If **exists but empty/malformed**: report corruption — `❌ Malformed: <file> — manual fix needed`
   - If **exists and valid**: report OK — `✅ <file>`
3. Check `schema_version` headers.
4. Report total memory size (approximate).

**Non-destructive principle:** Never overwrite a file that exists (even if malformed). Only recreate files that are completely missing. For corruption, report and let the user decide.

```
🔍 Memory Integrity Check:
✅ preferences.yml (valid, schema v1)
✅ rules.yml (valid, 4 rules, schema v1)
✅ context.yml (valid, schema v1)
⚠️ sessions/latest.json — missing, recreated
✅ tracking.yml (valid, schema v1)
📦 Total memory size: ~4.2 KB
```

---

### :rules touch Command

When the user types `:rules touch <id>`:

1. Find the rule by ID.
2. Update `last_used` to current timestamp.
3. Confirm: `✅ Marked [id] as still relevant.`

This prevents `:compact` from flagging actively-wanted rules as stale when they haven't been triggered organically.

---

<!-- PIPELINE EXECUTOR PROTOCOL — Integrated with Project Memory -->

## 🔄 Pipeline Executor Protocol

You have a built-in execution protocol for multi-step tasks. This ensures **every step is decomposed,
verified, and audited** — no steps are silently skipped.

### When to Activate Pipeline Mode

**Automatic activation** — enter pipeline mode when the task matches ANY of these concrete rules:

**Rule 1: Keyword triggers** — user message contains ANY of these words/phrases:
  - "set up", "setup", "install and configure", "bootstrap"
  - "deploy", "deployment", "release"
  - "migrate", "migration"
  - "configure", "configuration"
  - "follow the steps", "follow the guide", "follow the doc", "follow the runbook"
  - "do everything in", "run all the steps"
  - "pipeline", "run the pipeline"
  - "onboard", "onboarding"

**Rule 2: Multi-file edits** — task explicitly requires changing **3+ files**

**Rule 3: Explicit sequencing** — user describes steps with ordering words:
  - "first... then... after that..."
  - "step 1, step 2, step 3"
  - numbered lists with 3+ items

**Rule 4: References documentation** — user points to a doc/guide to follow:
  - "follow docs/deploy.md"
  - "use the README instructions"
  - "do what the runbook says"

**Manual activation** — user types `:pipeline` or `:pipeline <description>`

**When NOT to activate:**
- Simple questions ("What does this function do?")
- Single-file edits ("Fix the bug in auth.ts")
- Code review or explanation tasks
- Conversational responses
- Tasks with only 1-2 independent steps

When activating automatically, announce it and explain why:
```
🔄 Pipeline mode activated (reason: task contains "set up" + multi-step)
   I'll decompose this into verified steps for your approval.
```

The user can configure auto-detection via preferences:
```
:prefs set pipeline.auto_detect true       # enable (default)
:prefs set pipeline.auto_detect false      # disable — only :pipeline triggers
:prefs set pipeline.min_steps 3            # minimum steps to auto-activate
```

---

### The Protocol (MANDATORY when active)

When pipeline mode is active, you MUST follow this exact sequence. No exceptions.

#### Phase 1: DECOMPOSE

Break the task into the smallest possible atomic steps. Output:

```
═══ PIPELINE PLAN ═══
Task: <what the user asked>
Steps: <N>

  1. [step-id] — Description
     Depends on: (none | step-ids)
     Pre-check: what must be true before starting
     Post-check: how to verify it worked

  2. [step-id] — Description
     Depends on: [step-1]
     Pre-check: step-1 completed
     Post-check: expected outcome

  ...
═══════════════════
```

**Rules for decomposition:**
- Each step MUST have a single, clear action
- Each step MUST have at least one post-check (how do we know it worked?)
- Dependencies MUST be explicit
- If a step is optional, mark it: `(optional)`
- If a step can be retried, note it: `(retry: 3x)`

#### Phase 1b: STORE & APPROVE (the plan becomes a contract)

After decomposition, you MUST:

**1. Save the plan to project memory** as a YAML file:

Write to `~/.copilot/project-memory/<project>/pipelines/active-plan.yaml`:

```yaml
task: "Set up dev environment"
created_at: "2026-06-10T17:30:00Z"
status: "pending_approval"
steps:
  - id: check-python
    description: "Verify Python is installed"
    action: "python --version"
    depends_on: []
    prechecks: []
    postchecks:
      - "exit code 0"
    optional: false

  - id: install-deps
    description: "Install project dependencies"
    action: "pip install -r requirements.txt"
    depends_on: [check-python]
    prechecks:
      - "requirements.txt exists"
    postchecks:
      - "exit code 0"
      - "packages installed successfully"
    optional: false

  # ... all steps
```

**2. Show the workflow visually** to the user:

```
═══ PIPELINE WORKFLOW ═══
Task: Set up dev environment

  ┌─────────────────┐
  │ 1. check-python  │
  │ python --version │
  └────────┬────────┘
           ▼
  ┌──────────────────┐     ┌──────────────────┐
  │ 2. install-deps   │     │ 3. create-env     │
  │ pip install ...   │     │ (optional)        │
  └────────┬─────────┘     └────────┬─────────┘
           └────────┬───────────────┘
                    ▼
           ┌──────────────────┐
           │ 4. run-tests      │
           │ pytest tests/     │
           └──────────────────┘

  Steps: 4 (1 optional)
  Saved to: pipelines/active-plan.yaml

═══════════════════════════

⏳ Awaiting approval — proceed with this plan?
```

**3. ASK for approval** using the `ask_user` tool:

```
choices:
  - "✅ Approve — run this plan"
  - "✏️ Modify — I want to change some steps"
  - "❌ Cancel — don't run this"
```

**On approval responses:**
- **Approve** → update `status: "approved"` in the YAML file, proceed to Phase 2
- **Modify** → ask what to change, update the plan YAML, re-show workflow, re-ask
- **Cancel** → update `status: "cancelled"`, stop pipeline

**4. WHY this matters:**

The saved YAML file is the **source of truth** — not the AI's context window.
During Phase 2 (EXECUTE), you MUST:
- **Re-read** `pipelines/active-plan.yaml` before starting execution
- Execute steps **in the exact order defined in the file**
- Check off each step against the file — no additions, no removals, no reordering
- If a step was in the approved plan, it MUST be executed
- If a step was NOT in the approved plan, it MUST NOT be executed

This turns the AI's execution from "memory-based" to "file-based":
```
❌ Without stored plan: AI works from its context (lossy, can forget steps)
✅ With stored plan:    AI reads each step from disk (persistent, exact)
```

#### Phase 2: EXECUTE (one step at a time, reading from the stored plan)

**Before starting execution:**
1. Re-read `pipelines/active-plan.yaml` from project memory
2. Verify `status: "approved"` — do NOT execute unapproved plans
3. Update `status: "running"` in the file
4. Execute steps in the EXACT order defined in the file

For EACH step in the stored plan, output this EXACT structure:

```
━━━ STEP [N/total]: [step-id] ━━━

📋 PRE-CHECK:
  ✅ condition 1 (evidence: <what you checked>)
  ✅ condition 2 (evidence: <what you found>)
  — OR —
  ❌ condition 1 (evidence: <why it failed>) → STOPPING

🔨 EXECUTE:
  <do the actual work — run commands, edit files, etc.>

📋 POST-CHECK:
  ✅ condition 1 (evidence: <proof it worked>)
  ✅ condition 2 (evidence: <proof it worked>)
  — OR —
  ❌ condition 1 (evidence: <why it failed>) → STOPPING

📊 RESULT: ✅ PASSED | ❌ FAILED | ⏭️ SKIPPED (optional step)
```

**Execution rules:**
1. **NEVER skip a step.** Every step in the stored plan MUST appear in the output.
2. **NEVER proceed to step N+1 if step N failed**, unless it's marked optional.
3. **ALWAYS show evidence** — file paths, command output, exit codes. Not "I think it worked."
4. **If a pre-check fails on a required step**, STOP the pipeline immediately.
5. **If a post-check fails**, STOP and report what went wrong.
6. **Use real tool calls** for verification — actually run commands, check files, read output.
7. **Update the plan file** after each step completes — mark the step status in `active-plan.yaml`:
   ```yaml
   steps:
     - id: check-python
       status: completed        # ← updated after execution
       evidence: "Python 3.11.9"
     - id: install-deps
       status: running          # ← currently executing
   ```
   This means if the session crashes mid-pipeline, the plan file shows exactly where it stopped.
   On `:pipeline resume`, you can pick up from the last incomplete step.
8. **Cross-check against the plan:** After executing all steps, compare the step IDs you executed
   against the step IDs in `active-plan.yaml`. If ANY planned step was not executed, flag it.

**What counts as valid evidence:**
```
✅ Good evidence (deterministic, verifiable):
  - "File exists: src/config.ts (verified with ls)"
  - "Command exited with code 0: npm test"
  - "Output contains: 'All 42 tests passed'"
  - "Directory created: dist/ (3 files)"

❌ Bad evidence (not verifiable):
  - "I believe this worked"
  - "This should be fine"
  - "Done"
  - "The file was probably created"
```

#### Phase 3: REPORT

After ALL steps complete (or pipeline stops on failure):

**1. Update the plan file** with final status:
```yaml
status: "completed"  # or "failed" or "partial"
completed_at: "2026-06-10T17:45:00Z"
```

**2. Archive the plan**: Copy `active-plan.yaml` to `pipelines/<timestamp>-<task-slug>.yaml`
   so it's preserved in history. Clear `active-plan.yaml`.

**3. Output the summary:**

```
═══ PIPELINE REPORT ═══

Task: <original task>
Status: ✅ PASSED | ❌ FAILED at step [id] | ⚠️ PARTIAL (N/M steps)

  Step                    Status     Pre    Post   Evidence
  ─────────────────────────────────────────────────────────
  check-node              ✅ PASS    1/1    1/1    node v20.11.0
  install-deps            ✅ PASS    1/1    1/1    node_modules/ (1247 pkgs)
  run-tests               ✅ PASS    1/1    2/2    42 tests passing
  build                   ❌ FAIL    1/1    0/1    dist/ not created
  deploy                  🚫 BLOCKED  —      —     blocked by: build
  ─────────────────────────────────────────────────────────
  Total: 5 steps | ✅ 3 passed | ❌ 1 failed | 🚫 1 blocked

═══════════════════════
```

#### Phase 4: VALIDATE (automatic — like rubber-duck for pipelines)

**After completing Phase 3 (REPORT), you MUST run a validation pass.** This is NOT optional.
This works exactly like the rubber-duck agent — a separate, independent review of your own work.

**How to validate:**
Call the **rubber-duck agent** (via the `task` tool with `agent_type: "rubber-duck"`) with this prompt:

```
Review this pipeline execution for protocol compliance.

STORED PLAN FILE (source of truth — read from pipelines/active-plan.yaml):
<paste the full YAML plan that was approved by the user>

PIPELINE EXECUTION output:
<paste the full Phase 2 output>

PIPELINE REPORT:
<paste the Phase 3 report>

COMPLIANCE CHECKLIST — answer each with ✅ or ❌:
1. Was the task decomposed into atomic steps?
2. Does every step have at least one post-check?
3. Were ALL steps from the STORED PLAN executed (compare step IDs 1:1)?
4. Does every check have real, verifiable evidence (not "I think" or "should work")?
5. Did execution stop on failures (unless step was optional)?
6. Is the final report accurate and complete?
7. Were dependencies respected (no step ran before its deps)?
8. Are there steps that SHOULD have been in the plan but are missing?
9. Does the execution match the APPROVED plan exactly (no added/removed/reordered steps)?

For any ❌, specify:
- What was missed
- What needs to be redone
```

**After receiving validation results:**

- If ALL items are ✅ → proceed, pipeline is complete
- If ANY item is ❌ → you MUST fix the gaps:
  1. Show the user what the validator found
  2. Execute the missing/failed steps using the same Phase 2 format
  3. Re-run Phase 3 (updated REPORT)
  4. DO NOT re-validate (avoid infinite loops) — one validation pass is sufficient

**Example validator output:**
```
═══ PIPELINE VALIDATION ═══

  1. Task decomposed?           ✅
  2. Post-checks on all steps?  ✅
  3. No steps skipped?          ❌ Step "run-lint" was in plan but not executed
  4. Real evidence?             ✅
  5. Stopped on failure?        ✅
  6. Report accurate?           ❌ Report shows 5/5 but step 3 was skipped
  7. Dependencies respected?    ✅
  8. Missing steps?             ❌ No database migration step — task mentioned DB changes
  9. Matches approved plan?     ❌ Step "run-lint" in plan but missing from execution

  Verdict: ❌ FAILED — 3 issues found
  Action required: Execute "run-lint", add "db-migrate" step, update report

═══════════════════════════
```

**Why this works:**
- The validator is a SEPARATE agent call (structural, like rubber-duck)
- It independently reviews the execution — catches blind spots
- It checks against the STORED PLAN FILE, not just the output — detects skipped steps
- The main agent MUST act on findings — not just acknowledge them
- Combined with the structured format, this gives ~95% compliance

---

### :pipeline Command

| User Types | What To Do |
|-----------|------------|
| `:pipeline` | Show pipeline mode status and usage help |
| `:pipeline <task>` | Activate pipeline mode and start executing the task |
| `:pipeline resume` | Resume an interrupted pipeline from the last incomplete step |
| `:pipeline stop` | Deactivate pipeline mode for the rest of the session |
| `:pipeline last` | Show the last pipeline report from the current session |
| `:pipeline history` | Show all past pipeline runs for this project |
| `:pipeline auto on` | Enable auto-detection (default) |
| `:pipeline auto off` | Disable auto-detection — only manual `:pipeline` triggers it |

When user types `:pipeline` with no arguments, show:
```
🔄 Pipeline Executor — Deterministic Step Execution

  :pipeline <task>       Run a task in pipeline mode
  :pipeline resume       Resume an interrupted pipeline
  :pipeline stop         Disable pipeline mode
  :pipeline last         Show last pipeline report
  :pipeline history      Show all past runs
  :pipeline auto on|off  Toggle auto-detection (currently: on)

  Pipeline mode ensures every step is:
    ✅ Decomposed into atomic steps
    ✅ Saved to disk as a plan file (source of truth)
    ✅ Approved by user before execution
    ✅ Pre-checked before execution
    ✅ Post-checked with evidence
    ✅ Validated by independent agent (like rubber-duck)
    ✅ Audited in your session history

  Auto-activates for multi-step tasks (3+ steps).
  Say ":pipeline <task>" to manually trigger.
```

---

### Pipeline Integration with Project Memory

#### Directory Structure Update

```
~/.copilot/project-memory/<project>/
  ├── ...existing files...
  ├── tracking.yml        # Updated: includes pipeline tracking
  └── pipelines/          # NEW: pipeline plans and history
      ├── active-plan.yaml         # Currently running/pending plan
      └── <timestamp>-<slug>.yaml  # Archived completed plans
```

#### Session Auto-Save Integration

When a pipeline completes, include the report in the session JSON:

```json
{
  "sessionId": "<uuid>",
  "summary": "Ran pipeline: Deploy Service — 5/5 steps passed",
  "pipelines": [
    {
      "task": "Deploy Node.js Service",
      "status": "passed",
      "steps_total": 5,
      "steps_passed": 5,
      "steps": [
        { "id": "check-node", "status": "passed", "evidence": "node v20.11.0" }
      ]
    }
  ]
}
```

#### Tracking Integration

Track pipeline usage in `tracking.yml` under `pipeline:`:

```yaml
pipeline:
  total_runs: 12
  pass_rate: 0.83
  avg_steps: 6
  common_failures:
    - step_pattern: "install-deps"
      failure_count: 3
      common_cause: "network timeout"
      resolution: "retry with --prefer-offline"
  last_run: "2026-06-10T17:00:00Z"
```

After 3+ pipeline runs, if a step pattern fails repeatedly, suggest:
```
💡 I've noticed "install-deps" fails frequently (3 times).
Last fix: "retry with --prefer-offline". Want me to remember this as a rule?
```

#### Rules Integration

Pipeline mode respects project rules. For example:
- Rule: "Always run lint before commit" → pipeline auto-includes a lint step
- Rule: "Never deploy without tests passing" → pipeline adds test as a dependency of deploy
- Rule: "Use pnpm instead of npm" → pipeline uses pnpm commands

#### Preferences

Users can customize pipeline behavior via `:prefs`:

```yaml
pipeline:
  auto_detect: true          # Auto-activate for multi-step tasks (default: true)
  min_steps_to_activate: 3   # Minimum steps to auto-activate (default: 3)
  fail_fast: true            # Stop on first failure (default: true)
  show_evidence: true        # Always show evidence (default: true)
  save_to_session: true      # Save pipeline reports to session (default: true)
```

Set via: `:prefs set pipeline.auto_detect false`

### Why This Is More Reliable Than Generic Instructions

The pipeline protocol has **three enforcement layers** that generic instructions lack:

1. **Stored plan file** — Steps live on disk, not in AI's context window. The AI reads
   each step from `active-plan.yaml`, so it can't "forget" steps. If the session crashes,
   the file shows exactly where it stopped.

2. **User approval gate** — The user reviews and approves the plan before anything runs.
   The approved plan becomes a contract. No execution without explicit approval.

3. **Validator agent** — A separate rubber-duck agent independently compares the execution
   against the stored plan file. Catches skipped steps, fake evidence, and missing work.
   The main agent must fix any gaps found.

> Not 100% guaranteed — prompts are probabilistic. But non-compliance becomes **obvious**
> rather than **silent**. That's the key shift: from "hope the AI followed all steps" to
> "I can see and verify whether it did."

<!-- END PIPELINE EXECUTOR PROTOCOL -->

<!-- END PROJECT MEMORY SKILL -->
