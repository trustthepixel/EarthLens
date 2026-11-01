$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$hook = Join-Path $root '.git\hooks\pre-commit'
if (-not (Test-Path -LiteralPath (Join-Path $root '.git'))) {
    throw 'Git repository not found; initialize Git before installing hooks.'
}
$content = @'
#!/bin/sh
"./.venv/Scripts/python.exe" -m scripts.check_leaks
'@
[System.IO.File]::WriteAllText($hook, $content.Replace("`r`n", "`n") + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Output 'Installed .git/hooks/pre-commit.'
git hook run pre-commit
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
