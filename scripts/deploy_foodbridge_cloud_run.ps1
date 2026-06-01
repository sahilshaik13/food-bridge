# Deploy FoodBridge API + Next.js web to Cloud Run using repo root cloudbuild.yaml.
# Optionally syncs secrets from an env file first (see scripts/sync_env_to_gcp_secrets.ps1).
#
# From repo root:
#   gcloud auth login
#   gcloud config set project YOUR_GCP_PROJECT
#   .\scripts\deploy_foodbridge_cloud_run.ps1
#   .\scripts\deploy_foodbridge_cloud_run.ps1 -EnvFile ".env.production" -SyncSecrets -GrantSecretIam
#
param(
    [string]$EnvFile = ".env.local",
    [string]$ProjectId = "",
    [string]$Region = "asia-south1",
    [switch]$SyncSecrets,
    [switch]$GrantSecretIam
)

$ErrorActionPreference = "Stop"

function Parse-DotEnvFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return @{}
    }
    $dict = @{}
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -match '^\s*#' -or $line -eq "") { return }
        if ($line -match '^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $key = $Matches[1]
            $raw = $Matches[2].Trim()
            if ($raw.Length -ge 2) {
                $q = $raw[0]
                if (($q -eq '"' -or $q -eq "'") -and $raw.EndsWith($q)) {
                    $raw = $raw.Substring(1, $raw.Length - 2)
                }
            }
            $dict[$key] = $raw
        }
    }
    return $dict
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $ProjectId) {
    $ProjectId = gcloud config get-value project 2>$null
}
if (-not $ProjectId) {
    throw "Set GCP project: gcloud config set project YOUR_GCP_PROJECT_ID"
}

$envPath = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
$vars = Parse-DotEnvFile -Path $envPath

if ($SyncSecrets) {
    $syncArgs = @{ EnvFile = $EnvFile; ProjectId = $ProjectId }
    if ($GrantSecretIam) { $syncArgs.GrantIam = $true }
    & "$PSScriptRoot\sync_env_to_gcp_secrets.ps1" @syncArgs
}

# Build gcloud substitutions for Cloud Build (prefixed with _)
function Sub([string]$key, [string]$cloudBuildKey) {
    if ($vars.ContainsKey($key) -and -not [string]::IsNullOrWhiteSpace($vars[$key])) {
        return "${cloudBuildKey}=$($vars[$key])"
    }
    return $null
}

$pairs = @()
$s = Sub -key "GCP_REGION" -cloudBuildKey "_REGION"
if ($s) { $pairs += $s }
# Required overrides from env when present
@(
    @("_FIREBASE_PROJECT_ID", "FIREBASE_PROJECT_ID"),
    @("_FIREBASE_DATABASE_URL", "FIREBASE_DATABASE_URL"),
    @("_FIREBASE_STORAGE_BUCKET", "FIREBASE_STORAGE_BUCKET"),
    @("_FRONTEND_BASE_URL", "FRONTEND_BASE_URL"),
    @("_TELEGRAM_SLAVE_WEBHOOK_BASE_URL", "TELEGRAM_SLAVE_WEBHOOK_BASE_URL"),
    @("_NEXT_PUBLIC_API_BASE_URL", "NEXT_PUBLIC_API_BASE_URL"),
    @("_NEXT_PUBLIC_FIREBASE_API_KEY", "NEXT_PUBLIC_FIREBASE_API_KEY"),
    @("_NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN", "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN"),
    @("_NEXT_PUBLIC_FIREBASE_DATABASE_URL", "NEXT_PUBLIC_FIREBASE_DATABASE_URL"),
    @("_NEXT_PUBLIC_FIREBASE_PROJECT_ID", "NEXT_PUBLIC_FIREBASE_PROJECT_ID"),
    @("_NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET", "NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET"),
    @("_NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID", "NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID"),
    @("_NEXT_PUBLIC_FIREBASE_APP_ID", "NEXT_PUBLIC_FIREBASE_APP_ID"),
    @("_NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID", "NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID"),
    @("_NEXT_PUBLIC_GOOGLE_MAPS_API_KEY", "NEXT_PUBLIC_GOOGLE_MAPS_API_KEY"),
    @("_NEXT_PUBLIC_TIMER_ACCELERATION", "NEXT_PUBLIC_TIMER_ACCELERATION")
) | ForEach-Object {
    $s = Sub -key $_[1] -cloudBuildKey $_[0]
    if ($s) { $pairs += $s }
}

if ($pairs.Count -eq 0) {
    Write-Host "No overrides parsed from $envPath; using defaults in cloudbuild.yaml." -ForegroundColor Yellow
}
else {
    Write-Host "Applying $($pairs.Count) substitution override(s) from env (values hidden)." -ForegroundColor Cyan
}

$subArg = $pairs -join ","
if ($subArg) {
    gcloud builds submit . --config cloudbuild.yaml --project $ProjectId --substitutions $subArg
}
else {
    gcloud builds submit . --config cloudbuild.yaml --project $ProjectId
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host 'Done. Describe services:' -ForegroundColor Green
Write-Host ('  gcloud run services describe foodbridge-api --region ' + $Region + ' --format=value(status.url)')
Write-Host ('  gcloud run services describe foodbridge-web --region ' + $Region + ' --format=value(status.url)')
