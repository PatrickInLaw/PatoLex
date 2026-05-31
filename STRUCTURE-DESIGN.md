# PatoLex -- Structure Design Document

**Purpose:** This template provides a repository structure, documentation hierarchy, and Claude Code configuration baseline that reflects Patrick's general workflow for Microsoft-native (.NET / SQL Server / WinUI / WPF) projects with both Codex and Claude Code as collaborators. Lighter projects can drop sections; heavier projects can extend them.

---

## 1. Template Origin

This template was distilled in 2026-04 from two reference implementations:

- **KolaLaw-DB-2025 (Patito):** the heavyweight original -- Dataverse + WinUI MVVM + multi-gate roadmap + Codex + bump versioning.
- **PatoVideo:** a lighter video-processing tool that stripped Codex, versioning, and most tooling; retained docs skeleton.

The first version of this template (Sample_Repo.7z circa PatoVideo-setup) was *too thin* -- it included only the docs skeleton and missed the `.claude/` tooling that real Microsoft-stack projects depend on. This second iteration (post-PatoLex/cc001) reclaims the .NET / SQL / Codex tooling from KolaLaw and bakes in the lessons learned.

---

## 2. Repo Root Layout

```
/
├── CLAUDE.md
├── README.md
├── PROJECT_STRUCTURE.md
├── STRUCTURE-DESIGN.md          # this file
├── TEMPLATE-USAGE.md            # how to instantiate this template
├── .gitignore
├── .gitattributes
│
├── docs/                        # Documentation library
│   ├── README.md
│   ├── 00_Inbox/
│   │   └── comms/               # Codex CLI message exchange (to-codex.md, from-codex.md, transcript.md)
│   ├── 10_AUTHORITY_AND_RULES/
│   ├── 20_ROADMAP/
│   ├── 30_SYSTEM_DESIGN/
│   ├── 40_SCHEMA/
│   ├── 60_OPERATIONS/
│   ├── 80_PROJECT_HISTORY/
│   │   ├── CHANGELOG.md
│   │   ├── lessons/
│   │   ├── session-logs/
│   │   │   └── claude-code/
│   │   ├── run-logs/
│   │   └── audits/
│   └── 99_ARCHIVE/
│
├── src/                         # Application source code (TBD scaffolded)
├── tests/                       # Test suite
├── tools/                       # Supporting scripts/utilities
│
├── .claude/                     # Claude Code configuration
│   ├── settings.json            # Committed shared config (block-compound-bash hook + broad allow list)
│   ├── settings.local.json      # Per-machine overrides (Edit/Write/Bash blanket allows, pre-bash-check hook)
│   ├── commands/                # /ship, /bump, /deliver, /ucp, /verify, /codex-chat, /telegram-chat
│   ├── agents/                  # verify-auditor, telegram-monitor, submit-and-wait
│   ├── hooks/                   # pre-bash-check, block-compound-bash, haiku-delegation-nudge
│   ├── scripts/                 # ship.ps1, bump.ps1, telegram.ps1, comms-watcher.ps1, send_to_codex.ahk, nudge_codex.ps1
│   └── skills/                  # archive-repo, full 7-check verify SKILL
│
└── project-archives/            # Gitignored snapshots
```

---

## 3. What Came In and Why

### Hooks

| Hook | Why it's here |
|------|---------------|
| `pre-bash-check.ps1` | Session-log enforcement on commit/push, dotnet build version-bump enforcement, Codex review reminder, Telegram inbox check |
| `block-compound-bash.ps1` | Compound bash (`&&`, `||`, `;`, `cd`) causes endless permission prompts. **Non-negotiable.** |
| `haiku-delegation-nudge.ps1` | Optional token-conservation nudge after 4 consecutive Read/Grep/Glob calls. Off by default in `settings.json`. |

### Scripts

| Script | Purpose |
|--------|---------|
| `ship.ps1` | Bump-gated build + commit + push. Tolerant of pre-scaffold (no `*.sln` / `VersionInfo.cs`). |
| `bump.ps1` | Version bump (iteration / phase / subgate / gate:NN / set / show). Tolerant of missing `VersionInfo.cs` (writes bump-token only). |
| `telegram.ps1` | send / send-file / check via @PatoClaude_bot. Default tag: `[plx-cc]`. |
| `comms-watcher.ps1` | File-watcher transcript capture for Codex comms (long-running; run in a separate terminal). |
| `send_to_codex.ahk` | AutoHotkey nudge to the Codex CLI window. Targets `PatoLex_Codex` window title. |
| `nudge_codex.ps1` | PowerShell fallback for the AHK nudge. |

### Commands

| Command | Notes |
|---------|-------|
| `/ship` | Build + commit + push. |
| `/bump` | Version bump; `iteration` is default. |
| `/deliver` | Bump + ship in one step. |
| `/ucp` | Update session log, commit, push. |
| `/verify` | Spawn verify-auditor agent (sonnet for phase/subgate, opus for gate). |
| `/telegram-chat` | Bidirectional Telegram (`[plx-ccNN]` tag). |
| `/codex-chat` | Bidirectional Codex CLI comms. |

### Agents

| Agent | Default model | Notes |
|-------|---------------|-------|
| `verify-auditor` | sonnet | Adversarial audit. Override to opus for full-gate scope. |
| `telegram-monitor` | haiku | Background polling. |
| `submit-and-wait` | sonnet | Commit, push, send to Codex, poll for review. |

### Skills

| Skill | Notes |
|-------|-------|
| `archive-repo` | 7-Zip LZMA2 solid archive. Excludes `.git`, `.claude`, `bin`, `obj`, `models`, etc. |
| `verify` | 7-check adversarial audit (Codex-first with direct fallback). Domain-specific checks (DI, N+1, sync-over-async, layer violations) adapt as the project's architecture solidifies. |

---

## 4. What's Been Tuned vs. KolaLaw

- **Codex window title:** `PatoLex_Codex` (was hardcoded `CODEX_CX023` in KolaLaw). Generic names collide.
- **Bump infrastructure tolerates missing `VersionInfo.cs`:** so the hook doesn't block fresh repos that haven't scaffolded yet.
- **`ship.ps1` tolerates missing `*.sln`:** same reason -- pre-scaffold mode.
- **Co-author attribution is generic:** `Co-Authored-By: Claude Code <ClaudeCode@Kolasinski-Law.com>` -- no hardcoded model versions.
- **Session-log naming is the verbose KolaLaw form:** `SESSION_ccNNN_SUMMARY_2026-05-31_Title.md` -- browses much better than terse `ccNNN-summary.md`.
- **`block-compound-bash.ps1` is in by default** (KolaLaw-only feature; PatoVideo dropped it; the right call was to keep it).
- **`haiku-delegation-nudge.ps1` is included but not wired:** enable in `settings.json` if you want token-conservation enforcement.
- **`settings.json` hook config omits `"shell": "powershell"`:** that line causes `$CLAUDE_PROJECT_DIR` to be evaluated as a PowerShell variable (empty string), breaking the hook. Without it, Claude Code does the substitution correctly.
- **`settings.local.json` uses blanket allows (`Edit`, `Write`, `Bash`, etc.)** so per-edit prompts don't accumulate.

---

## 5. /verify Check Adaptation

The full 7-check verify SKILL is included. Domain-specific checks (DI registration, N+1 patterns, layer violations) reference the canonical Patito patterns; adapt them to the project's actual architecture once it solidifies. Universal checks (doc claims vs reality, stub returns, sync-over-async, test plan drift) apply to every project as-is.

---

## 6. .gitignore Defaults

- .NET build output (`bin`, `obj`, `TestResults`)
- Python build output (for auxiliary tooling)
- Audio binaries (mp3, wav, m4a, flac, ogg, aac, opus, wma) -- *trim if not relevant*
- Video binaries (mp4, avi, mkv, mov, wmv, flv, webm) -- *trim if not relevant*
- ML model weights (`*.pt`, `*.safetensors`, `*.gguf`, `*.onnx`, `models/`) -- *trim if not relevant*
- IDE files (.vs, .vscode, .idea)
- Visual Studio files
- Archives in `project-archives/`
- Environment / secrets (`.env`, `appsettings.Development.json`, etc.)
- Claude session-local state (`.claude/.bump-token`, `.claude/scripts/*.log`)

---

## 7. Implementation Order (For a New Repo)

1. Extract template, run the find-and-replace described in `TEMPLATE-USAGE.md`
2. Update `README.md` with the actual project description
3. Update `docs/20_ROADMAP/ROADMAP.md` with real milestones
4. Update `docs/30_SYSTEM_DESIGN/ARCHITECTURE.md` with the working vision
5. Update `docs/60_OPERATIONS/SETUP.md` with project-specific requirements
6. Trim `.gitignore` of binary categories that don't apply
7. Initial commit (one big commit covering steps 1-6)
8. Subsequent sessions: tech stack scaffold, then iterate per the roadmap

---

## Revision History

| Date | Change |
|------|--------|
| 2026-04-27 | Template v2: hybrid PatoVideo + KolaLaw-DB-2025 structure. Codex + bump + block-compound-bash + verbose session naming + generic co-author. Distilled from PatoLex cc001 setup. |
