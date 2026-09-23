# Launch the app. First run installs dependencies.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

Write-Host "Starting Conference Intelligence Assistant on http://localhost:8501" -ForegroundColor Green
.\.venv\Scripts\python.exe -m streamlit run app.py
