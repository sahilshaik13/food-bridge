# Creates or updates Secret Manager secrets used by Cloud Run (foodbridge-api).
# Run from repo root after: gcloud auth login && gcloud config set project YOUR_GCP_PROJECT
#
# Usage:
#   .\scripts\bootstrap_cloud_secrets.ps1
# Or pass values (otherwise prompted):
#   .\scripts\bootstrap_cloud_secrets.ps1 -OpenWeatherMapKey "xxx" -TelegramBotToken "123:ABC" -TelegramMasterSecret "secret"

param(
    [string]$OpenWeatherMapKey = "",
    [string]$TelegramBotToken = "",
    [string]$TelegramMasterSecret = ""
)

$ErrorActionPreference = "Stop"

function Upsert-SecretText {
    param([string]$Name, [string]$Value)
    if (-not $Value) { Write-Host "Skipping $Name (empty)." -ForegroundColor Yellow; return }
    $exists = gcloud secrets describe $Name 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Adding new version to secret: $Name"
        $Value | gcloud secrets versions add $Name --data-file=-
    } else {
        Write-Host "Creating secret: $Name"
        $Value | gcloud secrets create $Name --data-file=- --replication-policy=automatic
    }
}

if (-not $OpenWeatherMapKey) { $OpenWeatherMapKey = Read-Host "OPENWEATHERMAP_API_KEY (openweathermap.org)" }
if (-not $TelegramBotToken) { $TelegramBotToken = Read-Host "TELEGRAM_MASTER_BOT_TOKEN (BotFather @food_bridgebot or master bot)" }
if (-not $TelegramMasterSecret) { $TelegramMasterSecret = Read-Host "TELEGRAM_MASTER_SECRET (webhook secret_token)" }

Upsert-SecretText -Name "OPENWEATHERMAP_API_KEY" -Value $OpenWeatherMapKey
Upsert-SecretText -Name "TELEGRAM_MASTER_BOT_TOKEN" -Value $TelegramBotToken
Upsert-SecretText -Name "TELEGRAM_MASTER_SECRET" -Value $TelegramMasterSecret

Write-Host ""
Write-Host "Grant Cloud Run access (replace PROJECT_NUMBER and PROJECT_ID):" -ForegroundColor Cyan
Write-Host '  $PN = gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"'
Write-Host '  gcloud secrets add-iam-policy-binding OPENWEATHERMAP_API_KEY --member="serviceAccount:${PN}-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"'
Write-Host '  (repeat for TELEGRAM_MASTER_BOT_TOKEN, TELEGRAM_MASTER_SECRET)'
Write-Host ""
Write-Host "Cloud Build deploy SA also needs secretAccessor if builds deploy Cloud Run." -ForegroundColor Cyan
