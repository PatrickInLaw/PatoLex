Run: `powershell -ExecutionPolicy Bypass -File .claude/scripts/ship.ps1 -Message "<argument>"`

Argument = commit message (required). Report the script output. If it fails, show the error.

Flags (pass to the script as needed):
- `-SkipVersionCheck` -- skip the version-bump gate (e.g., docs-only commit)
- `-SkipBuild` -- skip dotnet build (e.g., before .NET project is scaffolded, or docs-only)

Pre-scaffold (no `*.sln` or `VersionInfo.cs` yet): the script auto-skips both gates.
