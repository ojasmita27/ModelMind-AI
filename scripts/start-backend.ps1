<# Starts the FastAPI backend on http://127.0.0.1:8000 (Ctrl+C to stop). #>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "Virtual environment missing. Run scripts\setup-local.ps1 first." -ForegroundColor Red; exit 1 }
Set-Location $backend

Write-Host "Applying database migrations (safe to repeat)..." -ForegroundColor Cyan
& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Write-Host "Migration failed. Read the message above." -ForegroundColor Red; exit 1 }

Write-Host "Checking configuration..." -ForegroundColor Cyan
& $py -m app.check_config
if ($LASTEXITCODE -ne 0) { Write-Host "Fix the problem above, then run this script again." -ForegroundColor Red; exit 1 }

Write-Host "`nStarting the API at http://127.0.0.1:8000  (docs: http://127.0.0.1:8000/docs)" -ForegroundColor Green
& $py -m uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000 --no-access-log
