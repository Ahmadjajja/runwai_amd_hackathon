# Run API from repo root (requires: pip install -r requirements.txt, copy .env.example -> .env)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "API: http://127.0.0.1:8000/health  |  model status: /api/model/status"
Write-Host "Frontend (new terminal): cd runwai\frontend ; python -m http.server 8080"
Write-Host ""
uvicorn runwai.server:app --reload --host 127.0.0.1 --port 8000
