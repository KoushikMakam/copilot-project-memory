
<!-- PROJECT MEMORY SKILL — v2 (slim) -->
<!-- Simple ops: AI handles inline. Complex ops: use copilot-memory CLI. -->

## 🧠 Project Memory

You have persistent project memory at `~/.copilot/project-memory/`.
Files are YAML (rules.yml, preferences.yml, context.yml, tracking.yml) + JSON (sessions/).

### Loading Memory

**On first reply**, say: `💡 Project memory available — type :status to load, or :resume to pick up where you left off.`

**On `:status` or `:resume`**: run `copilot-memory status` to get the overview, then read the relevant YAML files.

### Commands (user types these as chat messages)

**Simple ops — handle inline** (read/write YAML files directly):

| User types | What to do |
|-----------|------------|
| `:status` | Run `copilot-memory status` and show the output |
| `:resume` | Read `sessions/latest.json` → load the session JSON it points to → show summary |
| `:remember <rule>` | Read `rules.yml` from the project memory folder, append a new rule to the `rules:` list (see YAML Write Rules below), write the file back. Confirm what was added. |
| `:forget <id>` | Read `rules.yml`, remove the rule with matching `id` from the `rules:` list, write the file back. Confirm what was removed. |
| `:rules` | Read `rules.yml` from the project memory folder and display the rules in a readable table |
| `:prefs` | Read `preferences.yml` from the project memory folder and display key-value pairs |
| `:prefs set <k> <v>` | Read `preferences.yml`, set/update the key under the appropriate section, write back |
| `:context` | Read `context.yml` from the project memory folder and display it |
| `:sessions` | Run `copilot-memory session list` — show session IDs/summaries so you can reference them in stacks (`--repo NAME` or `--all-repos` for other repos) |
| `:help` | Show command list |

**Finding the project memory folder:**
1. Get the git root folder name (e.g., `my-project`)
2. Lowercase it, replace underscores with hyphens
3. Look for `~/.copilot/project-memory/<name>/` (e.g., `~/.copilot/project-memory/my-project/`)
4. If it doesn't exist, run `copilot-memory init` first

**Complex ops — use `copilot-memory` CLI** (deterministic, validated). `cmem` and `cm` are short aliases for `copilot-memory`:

| User types | Run this command |
|-----------|-----------------|
| `:verify` | `copilot-memory verify --fix` |
| `:compact` | `copilot-memory compact` |
| `:export team` | `copilot-memory export team` |
| `:init` | `copilot-memory init` |
| `:stacks` | `copilot-memory session stack list` |
| `:stack <name>` | `copilot-memory session stack show --stack <name>` — then load that layered context into working memory |
| `:stack save <name> <refs…>` | `copilot-memory session stack save <name> <refs…>` (base first → top last; add `--global` for cross-repo) |
| `:stack add <name> <refs…>` | `copilot-memory session stack save <name> <refs…> --append` |
| `:stack rm <name> [refs…]` | `copilot-memory session stack rm <name> [refs…]` (omit refs to delete the stack) |
| `:stack apply <name>` | `copilot-memory session stack apply --stack <name>` (materialize as one merged session) |
| `:layer <refs…>` | `copilot-memory session stack show <refs…>` — ad-hoc pick-and-choose, no save |

### Layered Context (Stacks)

A **stack** is a named, ordered *chained list* of sessions layered together so context
gets richer than a single `:resume`. You pick and choose exactly which sessions to layer,
**and stacks are composable and cross-repo** — a stack can reference other stacks and
sessions living in other repos (a "multi-repo session").

- **Reference grammar** (each entry, base → top):
  - `sessionId` — a session in the current repo
  - `@stackName` — another stack (chained list), inlined recursively (project or global)
  - `repo/sessionId` — a session in another repo's memory
  - `repo/@stackName` — another repo's stack, inlined
- **Ordering is base → top.** Later layers **win on conflicts** (treated as most recent).
- **Reusable profiles.** Save a stack per workstream, e.g. `common` for everyday work and
  `BMS` for BackupMgmt — each is its own chained list you reload anytime.
- **Cross-repo / global.** Save a multi-repo stack with `--global` (lives in `_global`) so
  it's reachable from any repo; resolution searches the current repo then global.
- **How to load:** when the user runs `:stack <name>` (or `:layer <refs…>`), run the
  matching `copilot-memory session stack show …` command, then treat the printed
  "Merged" decisions/learnings/files as active context for the rest of the conversation.
  The preview is produced by the same engine as `apply`, so it reflects exactly what
  `:stack apply` would persist. Each entry is tagged `⟵ <layers>` (its provenance); when
  two entries **contradict**, prefer the one from the **last/top** layer and flag the
  conflict to the user rather than silently keeping both.
- **Discover sessions to reference:** run `copilot-memory session list` (add `--repo NAME`
  or `--all-repos`) to see session IDs — it prints the exact `repo/sessionId` ref form.
- **Pick-and-choose:** `:layer <ref1> <ref2> …` layers arbitrary sessions/stacks on the fly
  without saving; `:stack save <name> <refs…>` persists the selection for reuse.
- **Materialize:** `:stack apply <name>` collapses the layers (even across repos) into one
  new merged session (records all layers under `parents`) so future auto-saves build on it.

Resolution is recursive with cycle detection (diamonds allowed, true cycles raise). `stack show`
previews the layered context using the same merge engine `stack apply` persists, so the preview
equals what gets materialized (deduped, order-preserving, older entries folded into
`compactedSummary`). Dedupe is exact-string only, so contradictory entries both survive; each is
annotated with its source layer(s) (`⟵ base, top`) so the AI/user can resolve conflicts (top layer
wins). `stack save` warns (doesn't block) on refs that don't resolve; `copilot-memory verify`
reports dangling stack refs.

### YAML Write Rules (when handling inline)

When writing YAML files, follow these exact patterns:

**Adding a rule** (`:remember never use any type`):
```yaml
# Append to the rules: list in rules.yml
- id: never-use-any-type          # lowercase, hyphens, max 50 chars, derived from the rule text
  type: dont                       # "do" if positive ("always X"), "dont" if negative ("never X")
  description: "never use any type"
  learned_from: "explicit instruction"
  created_at: "2026-06-11T12:00:00Z"
  last_used: "2026-06-11T12:00:00Z"
  use_count: 0
  share: false
```

**Removing a rule** (`:forget never-use-any-type`):
```yaml
# Read rules.yml, find the rule with id: never-use-any-type, remove it from the list, write back
```

**Setting a preference** (`:prefs set language python`):
```yaml
# In preferences.yml, under the appropriate section, set:
language: python
```

**Every YAML file MUST have** `schema_version: 1` as the first key. If missing, add it.

**Important:** Always read the full file first, modify in memory, then write the complete file back. Never partially write or append blindly.

### Session Auto-Save

After meaningful work (file edits, decisions, code generation), silently update or create
a session JSON in `sessions/_default/`:

```json
{
  "sessionId": "<uuid>",
  "status": "active",
  "startedAt": "<ISO>",
  "lastUpdatedAt": "<ISO>",
  "summary": "<1-line rolling summary>",
  "filesChanged": ["file1.ts", "file2.py"],
  "decisions": ["chose X over Y"],
  "learnings": ["user prefers Z"]
}
```

Update `sessions/latest.json` to point to the current session.

### Pipeline Mode (MANDATORY for multi-step tasks)

**⚠️ HARD GATE: For ANY task requiring 3+ sequential steps, you MUST show a plan and get approval BEFORE executing anything.**

**When to activate** — ANY of these triggers:
- User types `:pipeline`
- Message contains: `set up`, `setup`, `deploy`, `migrate`, `configure`, `bootstrap`, `onboard`, `follow the steps/guide/doc`, `end to end`, `step by step`, `full flow`
- Task requires 3+ sequential steps where order matters
- User points to a doc/guide to follow

**When pipeline activates, follow this EXACT sequence:**

1. **STOP** — Do NOT run any commands or make any changes yet
2. **DECOMPOSE** — Break the task into atomic steps with pre/post checks
3. **SHOW THE PLAN** — Present the plan to the user in this format:
   ```
   🔄 Pipeline mode activated (reason: <trigger>)

   ═══ PIPELINE PLAN ═══
   Task: <description>
   Steps: <N>

     1. [step-id] — Description
        Pre-check: what must be true
        Post-check: how to verify

     2. [step-id] — Description
        ...
   ═══════════════════
   ```
4. **ASK FOR APPROVAL** — Use `ask_user` tool with choices:
   - "✅ Approve — run this plan"
   - "✏️ Modify — I want to change some steps"
   - "❌ Cancel — don't run this"
5. **WAIT** — Do NOT proceed until the user explicitly approves
6. **EXECUTE** — Only after approval, save plan to `pipelines/active-plan.yaml` and execute step-by-step
7. **VERIFY** — Run `pipeline verify` after each step

**🚫 VIOLATION: Executing commands before showing a plan and receiving approval is a protocol violation. If you catch yourself about to run commands without approval, STOP immediately.**

Use `pipeline plan <yaml>` to generate a plan, `pipeline run <yaml>` to execute, and `pipeline verify <yaml>` to verify.

<!-- END PROJECT MEMORY SKILL -->
