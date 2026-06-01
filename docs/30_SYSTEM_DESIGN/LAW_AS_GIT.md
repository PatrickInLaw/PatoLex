# Law as a Git Repository

**Status:** Design decision (cc002, 2026-06-01). Shapes Gate D schema; features land in Gate H / post-launch.
**Related:** memory `law-as-git-repo`, `ROADMAP.md` (Gates D, H), event-sourced reconstruction (Method A).

---

## Premise

California's statutory history is a sequence of discrete, dated, authored changes to a body of text. That is exactly what a version-control system records. We adopt Git as a way to **model, distribute, and explore** the corpus — but **never** as the engine that *computes* what the law is.

The single most important rule in this document:

> **Git is a generated, read-only artifact emitted from our system of record. We never use Git's merge/conflict/rename machinery to reconcile competing changes. Our engine already knows where the conflicts are and how the law resolves them; Git only renders the resolved result.**

This is not a stylistic preference. Using Git's three-way text merge to reconcile two amendments would silently produce statute text **that was never enacted** (see "Why not the Git engine," below). The boundary is a correctness boundary.

---

## Three separable claims (only two are adopted)

The "law as Git" idea bundles three different propositions. We accept two and reject one.

| Claim | Adopted? | Rationale |
|-------|----------|-----------|
| **(1) Data model** — represent history with commit/branch/tag/blame primitives | **Yes** | 1:1 with the event-sourced schema we are already building. |
| **(2) Compute engine** — use Git's merge/conflict/rename detection to reconcile changes | **No** | Wrong semantics; would fabricate non-existent law. |
| **(3) Distribution artifact** — emit the corpus as a real clonable repo for pulls/clones/diffs/blame | **Yes — flagship** | Durable, portable, auditable; the handoff vehicle for perpetual stewardship. |

---

## Why not the Git engine (the trap, recorded so we never reconsider it)

Four reasons Git's machinery is the wrong tool for *computing* the law. Each is a way it would be silently, legally wrong:

1. **CA amendments are whole-section replacements, not patches.** Every amendment reads "Section X is amended to read as follows:" and restates the *entire* section. There is no line-level patch to three-way-merge; each change is effectively `checkout theirs` for one section-file.
2. **Reconciliation is by chapter order, not text overlap (Gov. Code §9605).** When two chaptered bills amend the same section in one session, the later-chaptered one prevails *as a whole*, even if the two edited different sentences. Git's three-way merge would *combine* two non-overlapping edits into a section that never existed in law.
3. **"Double-jointing = merge conflict" is inverted.** Double-jointing is the drafters *pre-resolving* the clash inside the bill so neither wipes the other. The real collision — "chaptering-out," the un-double-jointed case — does **not** halt like a Git conflict; the later chapter *silently* obliterates the earlier amendment. The legal event is an auto-resolved priority rule (closer to `merge -X theirs`). The valuable artifact is a **derived report** ("§X was chaptered-out in YYYY; here is the lost amendment") which our engine computes and we attach to the commit as a note — Git would never surface it.
4. **Recodification defeats rename detection.** 1872 and the 1943 Government Code split/merge/renumber sections (the Political Code was dissolved across multiple codes; one old section maps to several new ones). Git infers renames from content similarity and guesses this lineage wrong. Our explicit synthetic `section_id` lineage is exactly what Git cannot compute — though Git can faithfully *represent* it once we hand it the moves.

**Conclusion:** our reconstruction engine (Method A + §9605 resolution + lineage) decides what the law is and was. Git renders that decision. Never the reverse.

---

## Adopted concept mapping

| Legislative reality | Git primitive | Notes |
|---|---|---|
| A chaptered amendment (one act's effect) | A **commit** | Atomic, like the chapter itself. |
| The act / legislature | Commit **author** | e.g. `Stats. 1905 ch. 533`. |
| Operative date | Commit **date** | Enables `--before=DATE` point-in-time. |
| Chaptered date, effective date, bill #, chapter #, chapter-out flags | Commit **trailers / git notes** | Git has only two date slots; everything else rides in structured trailers. |
| In-force statewide law over time | **`main`** | A single operative timeline. |
| Recodification (1872, 1943) | A large `mv`+rewrite **commit** on `main` | Emitted *because* our lineage said so, not guessed. |
| Law as of date X | `rev-list -1 --before=X main` + checkout; session tags | Feature 1. |
| Which act last changed a section | `git blame` | Real attorney value; section-granular by nature, word-level diffs synthesized by us. |
| A pending / future bill | A **branch** off `main` (modern era only) | Feature 2; bill versions = commits on the branch. |

---

## Feature 1 — Point-in-time full-corpus clone (the static history repo)

**The deliverable:** a clonable repository, `ca-statutes` (or similar), whose history *is* California's statutory history. Clone it, check out any date, and you have the entire California statutory scheme exactly as it stood that day.

- **Layout:** one file per section, path encoding current code + section (e.g. `penal-code/0187.txt`), grouped by code/title/division. Path reflects *current* placement; lineage across renumbering is carried in the emitting DB and represented by the recodification commits' file moves.
- **Commits:** one per chaptered act, touching every section that act amended/added/repealed. Author = the act; date = operative date; trailers carry chaptered/effective dates, bill #, chapter #, and any chapter-out annotations.
- **Point-in-time:** because commit dates are operative dates, `git checkout $(git rev-list -1 --before=1888-04-12 main)` yields the law as of that day. We ship a one-line helper script (`as-of <date>`) and tag each legislative session for convenience.
- **Static by construction:** once the historical corpus (1850-present) is emitted, this history is **immutable**. It changes only by *appending* new commits as new law is enacted — never by rewriting. That immutability is what makes it safe to hand off.
- **Self-sufficient:** the repo is readable and useful with nothing but `git` — no database, no server, no PatoLex. This is the property that makes it the handoff vehicle (see Stewardship).

## Feature 2 — Live bill tracking (modern era and forward)

**The deliverable:** pending and future bills, each shown as a branch/PR-style diff against current `main`.

- Post-1991 we have successive bill versions from leginfo bulk data. An introduced bill = a **branch** off `main` at its introduction point; each amended version = a commit on that branch.
- A pending bill is, honestly, a pull request against the current law: a diff, an author, a status, a "will-merge-on-chaptering" date. A civic view — "the 14 open bills that would amend Penal Code §187, each as a diff against today's text" — is a genuinely novel feature.
- **Chaptering does NOT git-merge.** When a bill is chaptered, our engine resolves §9605 and computes the canonical result; the emitter then writes the resulting commit on `main` and marks the bill branch closed/merged with a reference to it. The branch is a *view of the proposal*; `main` is the *enacted result our engine produced*.
- This is the one piece that requires an **ongoing data feed** (leginfo). It is the primary live-maintenance surface and must be automated and low-touch so a modest steward can keep it running (scheduled pull -> DB update -> re-emit/append).

---

## Stewardship & perpetuity (why the repo is the gift)

**Intent (Patrick, cc002):** build PatoLex once to a trustworthy standard, then hand it to a law school or nonprofit to maintain in perpetuity — a gift to lawyers, students, and researchers. Distribution is free; no commercial driver.

This goal directly shapes the architecture:

- **The git repo, not the web app, is the durable artifact.** A Postgres DB + Vercel frontend needs funding, credentials, and ops to stay alive. A git repo can live on GitHub (or any mirror) for free, indefinitely, cloneable by anyone, and survives even if PatoLex's serving stack goes dark. The steward inherits something hard to kill.
- **Feature 1's repo is auditable by construction** — its commit log *is* its provenance — which is exactly the credibility property an academic steward wants.
- **Design for a modest maintainer:** deterministic, re-runnable emitter; documented; the only live surface (Feature 2's bill feed) automated and self-healing. The historical corpus, once emitted, needs no maintenance at all.
- **Licensing (to confirm at Gate H):** statutory text is public domain (government edicts; Gov. Code §10248.5) — dedicate repo *content* CC0 / public-domain; PatoLex *tooling* under a permissive license (MIT/Apache). Note the channel-terms constraint from `DATA_SOURCES_HISTORICAL.md` §1a still binds *acquisition* sources, but the emitted public-domain text is unencumbered.

---

## Schema implications for Gate D (act on these now)

The event-sourced schema must carry everything the emitter will later need, or we'll be backfilling. Each change-event must record:

- **section lineage** (synthetic `section_id` surviving renumbering/recodification) -> drives file paths + `mv` commits;
- **three dates** (chaptered, effective, operative) -> commit date + trailers;
- **act identity** (statute citation, chapter #, bill #, legislature/session) -> commit author + trailers;
- **action type** (amend / add / repeal / recodify) -> commit shape;
- **resolution metadata** (§9605 winner, chaptered-out losers, double-jointing references) -> derived chapter-out notes;
- **provenance + trust level** per version -> trailers (audit transparency for the steward).

If the schema carries these, the Git emitter is a downstream, deterministic projection. If it doesn't, the Git features are blocked. **Therefore Gate D designs with the emitter's needs as a first-class requirement.**

---

## Open questions (carried to Gate D/H)

- Commit granularity: strictly one-commit-per-act, or split very large recodification acts for navigability?
- Tagging scheme: per session, per year, per code-version — what do attorneys actually want to check out?
- Repo scale: 1850-present, all codes, every amendment = a deep history; validate `blame`/`log` performance and consider per-code repos vs. one monorepo.
- Word-level diff synthesis: we generate intra-section word diffs (the law only restates whole sections) — store or compute on demand?
- Feature 2 feed cadence and the exact branch/close protocol on chaptering.
