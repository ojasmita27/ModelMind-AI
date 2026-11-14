<# Runs ALL automated checks: backend tests, frontend typecheck, frontend tests, frontend build. #>
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "Run scripts\setup-local.ps1 first." -ForegroundColor Red; exit 1 }
$failed = @()

Push-Location (Join-Path $root "backend")
Write-Host "`n==> Backend tests (pytest, isolated temporary SQLite database)" -ForegroundColor Cyan
& $py -m pytest
if ($LASTEXITCODE -ne 0) { $failed += "backend pytest" }
Pop-Location

Push-Location (Join-Path $root "frontend")
Write-Host "`n==> Frontend typecheck" -ForegroundColor Cyan
npm run typecheck
if ($LASTEXITCODE -ne 0) { $failed += "frontend typecheck" }
Write-Host "`n==> Frontend tests (vitest)" -ForegroundColor Cyan
npm test
if ($LASTEXITCODE -ne 0) { $failed += "frontend tests" }
Write-Host "`n==> Frontend production build" -ForegroundColor Cyan
npm run build
if ($LASTEXITCODE -ne 0) { $failed += "frontend build" }
Pop-Location

if ($failed.Count -eq 0) { Write-Host "`nAll checks passed." -ForegroundColor Green; exit 0 }
Write-Host "`nFAILED: $($failed -join ', ')" -ForegroundColor Red; exit 1
