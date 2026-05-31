Run: `powershell -ExecutionPolicy Bypass -File .claude/scripts/bump.ps1 -BumpType "<argument or iteration>"`

Argument: `iteration` (default), `phase`, `subgate`, `gate:NN`, `set:x.x.x.x.x`, or `show`. Report the script output.

Pre-scaffold (no `VersionInfo.cs` yet): the script writes only the bump-token sentinel so build enforcement works once the .NET project is added.
