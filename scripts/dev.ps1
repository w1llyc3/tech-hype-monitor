#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example"
}

$ApiDir = Join-Path $Root "apps\api"
$WebDir = Join-Path $Root "apps\web"
$VenvPython = Join-Path $ApiDir ".venv\Scripts\python.exe"
$VenvPip = Join-Path $ApiDir ".venv\Scripts\pip.exe"

if (-not (Test-Path $VenvPython)) {
  Write-Host "Creating API virtualenv..."
  python -m venv (Join-Path $ApiDir ".venv")
  & $VenvPip install -r (Join-Path $ApiDir "requirements.txt")
}

Write-Host "Running migrations..."
Push-Location $ApiDir
& $VenvPython -m alembic upgrade head
& $VenvPython -m app.db.seed
Pop-Location

if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
  Write-Host "Installing web dependencies..."
  Push-Location $WebDir
  npm install
  Pop-Location
}

Write-Host "Starting API on http://localhost:8000 ..."
$api = Start-Process -PassThru -NoNewWindow -FilePath $VenvPython -ArgumentList @(
  "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"
) -WorkingDirectory $ApiDir

Write-Host "Starting Web on http://localhost:3000 ..."
$web = Start-Process -PassThru -NoNewWindow -FilePath "npm" -ArgumentList @("run", "dev") -WorkingDirectory $WebDir

Write-Host ""
Write-Host "API: http://localhost:8000"
Write-Host "Web: http://localhost:3000"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

try {
  Wait-Process -Id $api.Id, $web.Id
} finally {
  if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
  if (-not $web.HasExited) { Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue }
}
