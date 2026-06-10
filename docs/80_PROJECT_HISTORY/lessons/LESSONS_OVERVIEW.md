# Lessons Overview

Index of lessons learned during the PatoLex project.

## Inherited Lessons (from Pato template, 2026-04-27)

These lessons came from the template's own setup history and apply to any new repo using this template:

- **Don't hardcode model versions in tooling.** Co-author attribution should be `Claude Code <ClaudeCode@Kolasinski-Law.com>` -- survives model upgrades without churn.
- **`block-compound-bash.ps1` is non-negotiable.** Compound bash (`&&`, `||`, `;`, `cd ...`) causes endless permission prompts. Hook included by default in this template; do not disable.
- **Verbose session-log naming wins.** `SESSION_ccNNN_SUMMARY_YYYY-MM-DD_Title.md` browses much better in Explorer than `ccNNN-summary.md`.
- **Bump enforcement must tolerate missing VersionInfo.cs.** Pre-scaffold mode is built into `bump.ps1` and the pre-bash hook; do not remove the file-existence checks.
- **Parallelize template-porting and other mechanical work.** Repo setup is mostly content adaptation of known files. Batch by directory and dispatch parallel Sonnet/Haiku subagents -- don't sequence Opus through it. Estimated savings: ~3/4 wall-clock time, ~1/2 tokens.
- **Codex window title should be project-specific.** This repo uses `PatoLex_Codex`.
- **Hooks: omit `"shell": "powershell"` in settings.json.** Setting this causes `$CLAUDE_PROJECT_DIR` to be evaluated as a PowerShell variable (empty), breaking the path. Let Claude Code do the substitution by leaving the field out.

## PatoLex-Specific Lessons (cc001)

- **Supabase port rule (applies to the future Supabase serving deployment, not the current build DB):** use port 6543 (PgBouncer) for Vercel serverless functions; port 5432 (direct) for any long-running pipeline process. Serverless functions exhaust the 60-connection limit on the direct URL. **Currently (2026-06-09): the active DB is local PostgreSQL 16 at `localhost:5432/patolex` — Supabase is a planned future serving deployment only.**
- **`service_role` key must never appear in client-side code.** Use `anon` key for browser-facing calls; `service_role` only in Next.js Server Components / Route Handlers / tRPC procedures running server-side.
- **Read the template FIRST, then build.** On cc001, the agent started building before fully reviewing the sample repo and had to stop and restart. Cost: extra time and context. Rule: always extract and read the full template before touching the new repo.
- **Write tool requires Read first.** Claude Code's Write tool will refuse to overwrite a file it hasn't read this session. On large repo setups, batch-read target files before batch-writing, or accept the read-then-write sequence for each file.

---

## Dated Lesson Files (pipeline / ops)

- **[LESSON_2026-06-02_ocr_cpu_prep_bottleneck.md](LESSON_2026-06-02_ocr_cpu_prep_bottleneck.md)** — OCR throughput is CPU-prep-bound, not GPU-bound; 3/1 is the proven worker config.
- **[LESSON_2026-06-03_ops_temp_logging_and_elevation.md](LESSON_2026-06-03_ops_temp_logging_and_elevation.md)** — ops temp logging + elevation.
- **[LESSON_2026-06-05_stage05_mojibake_detection.md](LESSON_2026-06-05_stage05_mojibake_detection.md)** — born-digital STAGE 0.5 mojibake detection / OCR fallback.
- **[LESSON_2026-06-06_prep_runner_ram_oom_5080.md](LESSON_2026-06-06_prep_runner_ram_oom_5080.md)** — `prep_runner.py --parallel 8/16` OOMs the 16 GB 5080 box (RAM, not VRAM); use the single-worker `run_worker_5080.py` with a RAM guard instead.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc001: Initial version with inherited template lessons + PatoLex-specific lessons. |
| 2026-06-06 | Added "Dated Lesson Files" index section (the dated LESSON_*.md files were previously unindexed); added the prep_runner RAM-OOM lesson. |
