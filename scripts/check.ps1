$ErrorActionPreference = 'Stop'
$failed = $false
$python = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
$python = [System.IO.Path]::GetFullPath($python)

$tests = Join-Path $PSScriptRoot '..\tests'
$testFiles = if (Test-Path -LiteralPath $tests) { @(Get-ChildItem -LiteralPath $tests -Filter 'test_*.py' -File -Recurse) } else { @() }
if ($testFiles.Count -gt 0) {
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { $failed = $true }
} else {
    Write-Output 'No pytest tests found; skipping pytest.'
}

& $python -m scripts.check_leaks
if ($LASTEXITCODE -ne 0) { $failed = $true }
& $python -m scripts.check_language
if ($LASTEXITCODE -ne 0) { $failed = $true }

if ($failed) {
    Write-Output 'CHECK FAILED'
    exit 1
}
Write-Output 'CHECK OK'
