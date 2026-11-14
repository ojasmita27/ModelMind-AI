<#
  ModelMind AI: one-time local setup (SQLite mode, no Docker).
  Run from the project root:
      powershell -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
  Safe to run again. It NEVER overwrites an existing .env or deletes your data.
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($message) { Write-Host "`n==> $message" -ForegroundColor Cyan }
function Fail($message) { Write-Host "`nERROR: $message" -ForegroundColor Red; exit 1 }
function Run-Checked($exe, $arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Fail "Command failed: $exe $($arguments -join ' ')" }
}

# ---- 1. Python 3.11+ ---------------------------------------------------------
Step "Looking for Python 3.11 or newer"
$pythonCmd = $null
foreach ($candidate in @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3"), @("python"))) {
    $extra = @()
    if ($candidate.Count -gt 1) { $extra = $candidate[1..($candidate.Count - 1)] }
    try {
        $text = (& $candidate[0] @extra --version 2>&1) | Out-String
        if ($text -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -eq 3 -and $minor -ge 11) { $pythonCmd = $candidate; Write-Host "Found $($text.Trim())"; if ($minor -gt 12) { Write-Host "Note: the project was tested on Python 3.12." -ForegroundColor Yellow }; break }
        }
    } catch { }
}
if (-not $pythonCmd) { Fail "Python 3.11+ not found. Install it from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'." }
$pyExe = $pythonCmd[0]
$pyExtra = @()
if ($pythonCmd.Count -gt 1) { $pyExtra = $pythonCmd[1..($pythonCmd.Count - 1)] }

# ---- 2. Node 20.19+ ----------------------------------------------------------
Step "Checking Node.js (20.19 or newer)"
try { $nodeText = (& node --version 2>&1) | Out-String } catch { $nodeText = "" }
if ($nodeText -notmatch "v(\d+)\.(\d+)") { Fail "Node.js not found. Install the LTS version from https://nodejs.org/ and reopen PowerShell." }
$nodeMajor = [int]$Matches[1]; $nodeMinor = [int]$Matches[2]
if ($nodeMajor -lt 20 -or ($nodeMajor -eq 20 -and $nodeMinor -lt 19)) { Fail "Node.js $($nodeText.Trim()) is too old. Install Node 20.19 or newer (the current LTS is fine)." }
Write-Host "Found Node $($nodeText.Trim())"

# ---- 3. Backend virtual environment -----------------------------------------
Step "Creating the backend virtual environment (backend\.venv)"
$venvPython = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Run-Checked $pyExe (@($pyExtra) + @("-m", "venv", "backend\.venv"))
} else { Write-Host "Already exists. Reusing it." }

Step "Installing backend dependencies"
Run-Checked $venvPython @("-m", "pip", "install", "--upgrade", "pip", "--quiet")
Run-Checked $venvPython @("-m", "pip", "install", "-r", "backend\requirements-dev.txt", "--quiet")

# ---- 4. .env (never overwritten) --------------------------------------------
Step "Preparing .env"
$envFile = Join-Path $root ".env"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
if (Test-Path $envFile) {
    Write-Host ".env already exists. Leaving it untouched."
    if ((Get-Content $envFile -Raw) -match "(?m)^SECRET_KEY=.*CHANGE_ME") {
        Write-Host "WARNING: SECRET_KEY in .env still has the CHANGE_ME placeholder. Replace it before starting the backend." -ForegroundColor Yellow
    }
} else {
    $key = (& $venvPython -c "import secrets; print(secrets.token_urlsafe(48))" | Out-String).Trim()
    if ($key.Length -lt 32) { Fail "Could not generate a secret key." }
    $template = [System.IO.File]::ReadAllText((Join-Path $root ".env.example"))
    $content = [regex]::Replace($template, "(?m)^SECRET_KEY=.*$", "SECRET_KEY=$key")
    [System.IO.File]::WriteAllText($envFile, $content, $utf8NoBom)
    Write-Host "Created .env with a freshly generated SECRET_KEY (SQLite mode)."
}

# ---- 5. Database migration ---------------------------------------------------
Step "Creating the local database (alembic upgrade head)"
Push-Location (Join-Path $root "backend")
try { Run-Checked $venvPython @("-m", "alembic", "upgrade", "head") } finally { Pop-Location }

# ---- 6. Frontend dependencies ------------------------------------------------
Step "Installing frontend dependencies (npm install)"
Push-Location (Join-Path $root "frontend")
try { Run-Checked "npm" @("install") } finally { Pop-Location }

Write-Host "`nSetup complete." -ForegroundColor Green
Write-Host "Start the app in TWO terminals:"
Write-Host "  Terminal 1:  powershell -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1"
Write-Host "  Terminal 2:  powershell -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1"
Write-Host "Then open http://localhost:5173"
