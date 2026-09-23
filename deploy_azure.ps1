# Deploy the app to Azure App Service (Linux).
#
#   .\deploy_azure.ps1 -AppName iqhack-conf-intel
#
# Requires Azure CLI and a subscription you can create resources in.
# Add -RestrictToTenant to require an IQVIA sign-in before the app is reachable.

param(
    [Parameter(Mandatory = $true)][string]$AppName,
    [string]$ResourceGroup = "rg-iqhack-conf-intel",
    [string]$Location      = "westeurope",
    [string]$Sku           = "B1",
    [switch]$RestrictToTenant
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }

# --- preflight ---------------------------------------------------------------
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI not found. Install it, then open a NEW terminal."
}

$account = az account show 2>$null | ConvertFrom-Json
if (-not $account) {
    Step "Signing in to Azure"
    az login | Out-Null
    $account = az account show | ConvertFrom-Json
}
Write-Host "Subscription : $($account.name)" -ForegroundColor DarkGray
Write-Host "Tenant       : $($account.tenantId)" -ForegroundColor DarkGray

$plan = "$AppName-plan"

# --- infrastructure ----------------------------------------------------------
Step "Creating resource group $ResourceGroup"
az group create --name $ResourceGroup --location $Location --output none

Step "Creating App Service plan ($Sku, Linux)"
az appservice plan create --name $plan --resource-group $ResourceGroup `
    --location $Location --sku $Sku --is-linux --output none

Step "Creating web app $AppName"
az webapp create --name $AppName --resource-group $ResourceGroup `
    --plan $plan --runtime "PYTHON:3.12" --output none

# --- configuration -----------------------------------------------------------
Step "Enabling WebSockets (Streamlit will not work without this)"
az webapp config set --name $AppName --resource-group $ResourceGroup `
    --web-sockets-enabled true --output none

Step "Setting startup command"
az webapp config set --name $AppName --resource-group $ResourceGroup `
    --startup-file "bash startup.sh" --output none

Step "Setting application settings"
# /home is the only path that survives a restart on App Service.
$settings = @(
    "CI_DATA_DIR=/home/data",
    "SCM_DO_BUILD_DURING_DEPLOYMENT=true",
    "WEBSITES_CONTAINER_START_TIME_LIMIT=600"
)
if ($env:CI_PROVIDER)   { $settings += "CI_PROVIDER=$env:CI_PROVIDER" }
if ($env:CI_TEXT_MODEL) { $settings += "CI_TEXT_MODEL=$env:CI_TEXT_MODEL" }
if ($env:CI_VISION_MODEL) { $settings += "CI_VISION_MODEL=$env:CI_VISION_MODEL" }
az webapp config appsettings set --name $AppName --resource-group $ResourceGroup `
    --settings $settings --output none

Write-Host "`nNOTE: set the API key separately so it is never written to a file:" -ForegroundColor Yellow
Write-Host "  az webapp config appsettings set -n $AppName -g $ResourceGroup --settings AZURE_OPENAI_API_KEY=<key>" -ForegroundColor White

# --- package -----------------------------------------------------------------
Step "Packaging application"
$zip = Join-Path $env:TEMP "$AppName-deploy.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }

$staging = Join-Path $env:TEMP "$AppName-staging"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null

$exclude = @(".venv", "data", "__pycache__", ".git", ".streamlit\secrets.toml")
Get-ChildItem -Path . -Force | Where-Object {
    $_.Name -notin @(".venv", "data", "__pycache__", ".git") -and $_.Name -ne ".env"
} | ForEach-Object {
    Copy-Item $_.FullName -Destination $staging -Recurse -Force
}
Get-ChildItem $staging -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

Compress-Archive -Path "$staging\*" -DestinationPath $zip -Force
Write-Host "Package: $([math]::Round((Get-Item $zip).Length / 1KB)) KB" -ForegroundColor DarkGray

# --- deploy ------------------------------------------------------------------
Step "Deploying (first build takes several minutes)"
az webapp deploy --name $AppName --resource-group $ResourceGroup `
    --src-path $zip --type zip --output none

# --- optional access control -------------------------------------------------
if ($RestrictToTenant) {
    Step "Requiring Entra ID sign-in"
    az webapp auth microsoft update --name $AppName --resource-group $ResourceGroup `
        --issuer "https://sts.windows.net/$($account.tenantId)/" `
        --yes --output none
    az webapp auth update --name $AppName --resource-group $ResourceGroup `
        --enabled true --action RedirectToLoginPage --output none
    Write-Host "App now requires an organisational sign-in." -ForegroundColor Green
} else {
    Write-Host "`nWARNING: the app is PUBLIC. Anyone with the URL can use it and spend" -ForegroundColor Yellow
    Write-Host "your API credits. Re-run with -RestrictToTenant to require a sign-in." -ForegroundColor Yellow
}

Step "Done"
Write-Host "https://$AppName.azurewebsites.net" -ForegroundColor Green
Write-Host "`nLogs:   az webapp log tail -n $AppName -g $ResourceGroup"
Write-Host "Delete: az group delete -n $ResourceGroup --yes --no-wait"
