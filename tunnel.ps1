# Publish the locally running app on a public HTTPS URL via Cloudflare Tunnel.
#
#   .\tunnel.ps1
#
# The app keeps running on this machine -- nothing is uploaded anywhere, so the
# API key and captured conference data never leave the laptop. The URL is valid
# only while this window stays open.

param([int]$Port = 8501)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Pick up cloudflared if it was installed in this session without a new shell.
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "cloudflared not found. Install it with:" -ForegroundColor Red
    Write-Host "  winget install --id Cloudflare.cloudflared" -ForegroundColor White
    exit 1
}

if (-not (netstat -ano | Select-String ":$Port\s+.*LISTENING")) {
    Write-Host "Nothing is listening on port $Port." -ForegroundColor Red
    Write-Host "Start the app first in another terminal:  .\run.ps1" -ForegroundColor White
    exit 1
}

# The app records its gate state on startup, because $env: in this terminal says
# nothing about the terminal the app was launched from.
$marker = Join-Path $PSScriptRoot "data\.gate"
$gateOn = (Test-Path $marker) -and ((Get-Content $marker -Raw).Trim() -eq "1")

if ($gateOn) {
    Write-Host "Access code gate is ON." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "WARNING: the running app has no access code." -ForegroundColor Yellow
    Write-Host "The public URL will be open to anyone who has it. They could upload" -ForegroundColor Yellow
    Write-Host "files and spend your API credits. To gate it, stop the app, then in" -ForegroundColor Yellow
    Write-Host "THE SAME terminal you start the app from, run:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host '  $env:CI_APP_PASSWORD = "your-code"' -ForegroundColor White
    Write-Host "  .\run.ps1" -ForegroundColor White
    Write-Host ""
    $answer = Read-Host "Continue without an access code? (y/N)"
    if ($answer -ne "y") { exit 0 }
}

Write-Host ""
Write-Host "Starting tunnel. Look for the https://<something>.trycloudflare.com URL below." -ForegroundColor Cyan
Write-Host "Keep this window open for as long as you need the URL. Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

cloudflared tunnel --url "http://localhost:$Port"
