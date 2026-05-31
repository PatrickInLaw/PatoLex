---
name: archive-repo
description: Create a compressed archive of the entire repository in project-archives/ using 7-Zip LZMA2 solid compression (.7z). Use --compat for LZMA-in-ZIP format. Follows 2026-05-31-HH-MM-Description naming convention.
disable-model-invocation: false
argument-hint: "<description> [--keep] [--compat]"
---

# Archive Repository

Create a compressed archive of the repository and store it in `project-archives/`.

## Arguments

- `$ARGUMENTS` should contain the **description** portion of the filename (e.g., `Full-Repo-Snapshot`, `After-Milestone-1`)
- `--keep` -- preserve all existing archives in `project-archives/`
- `--compat` -- produce a `.zip` file (LZMA method) instead of `.7z` for broader compatibility

If `--keep` is NOT present, **delete all pre-existing archive files** (`.7z` and `.zip`) in `project-archives/` after the new archive is successfully created.

## Naming Convention

```
{2026-05-31-HH-MM}-{Description}.7z      (default)
{2026-05-31-HH-MM}-{Description}.zip     (with --compat)
```

- Date and time in **Pacific Time** (PDT/PST)
- Description is taken from the argument, with spaces replaced by hyphens

## Exclusions

Exclude these directories from the archive:
- `.git/`
- `.claude/`
- `.vs/`
- `project-archives/`
- `bin/`
- `obj/`
- `node_modules/`
- `TestResults/`
- `__pycache__/`
- `models/` (large ML weights)

## 7-Zip Requirement

This skill requires 7-Zip. Before archiving, check for 7-Zip:

```bash
which 7z 2>/dev/null || "/c/Program Files/7-Zip/7z.exe" --help 2>/dev/null | head -1
```

If 7-Zip is **not found**, ask the user:

> 7-Zip is not installed. Install it? On Windows: `winget install 7zip.7zip`

Do NOT proceed without 7-Zip. Do NOT fall back to PowerShell Compress-Archive or other tools.

## Steps

1. Parse `$ARGUMENTS` to extract the description and check for `--keep` and `--compat` flags
2. Verify 7-Zip is available (see above)
3. Generate the timestamp in Pacific Time: `date -u -d '-7 hours' +%Y-%m-%d-%H-%M`
4. Build the filename with the appropriate extension (`.7z` or `.zip`)
5. Create the archive from the repository root:

   **Default (LZMA2 solid .7z):**
   ```bash
   7z a -t7z -mx=9 -m0=LZMA2 -ms=on "project-archives/{filename}" . \
     -xr!.git -xr!.claude -xr!.vs -xr!project-archives \
     -xr!bin -xr!obj -xr!node_modules -xr!TestResults -xr!__pycache__ -xr!models
   ```

   **With --compat (LZMA .zip):**
   ```bash
   7z a -tzip -mm=LZMA -mx=9 "project-archives/{filename}" . \
     -xr!.git -xr!.claude -xr!.vs -xr!project-archives \
     -xr!bin -xr!obj -xr!node_modules -xr!TestResults -xr!__pycache__ -xr!models
   ```

6. Unless `--keep` was specified, delete all **pre-existing** archive files in `project-archives/` (do NOT delete the archive just created)
7. **Git commit and push:**
   - Stage the new archive and any deleted archives: `git add project-archives/`
   - Commit with message describing the archive
   - Push to the current branch: `git push`
8. Report:
   - Archive filename and full path
   - Archive size
   - Compression method used (LZMA2 solid or LZMA ZIP)
   - Whether prior archives were kept or removed
   - Commit hash and push status
