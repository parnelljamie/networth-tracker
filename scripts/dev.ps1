# Runs the backend (uvicorn --reload) and frontend (vite) dev servers side by side.
# Browse http://localhost:5173 — Vite proxies /api to the backend on :8000.
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$repoRoot\backend'; uv run uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$repoRoot\frontend'; npm run dev"

Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Frontend: http://localhost:5173"
