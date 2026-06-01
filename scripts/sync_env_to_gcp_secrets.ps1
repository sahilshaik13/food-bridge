# Sync selected keys from a .env-style file to Google Secret Manager (create or new version).
# Does not print secret values. Skips empty values and path-like values (e.g. *.json credentials).
#
# Usage (from repo root):
#   gcloud config set project YOUR_GCP_PROJECT
#   .\scripts\sync_env_to_gcp_secrets.ps1
#   .\scripts\sync_env_to_gcp_secrets.ps1 -EnvFile ".\backend\.env.local" -GrantIam
#
param(
    [string]$EnvFile = ".env.local",
    [string]$ProjectId = "",
    [switch]$GrantIam,
    # Keys always considered when present and non-empty (names must match Secret Manager secret ids).
    [string[]]$IncludeKeys = @(
        "OPENWEATHERMAP_API_KEY",
        "TELEGRAM_MASTER_BOT_TOKEN",
        "TELEGRAM_MASTER_SECRET",
        "REPORT_VERIFY_SECRET",
        "SCHEDULER_JOB_SECRET",
        "SMTP_PASS"
    )
)

$ErrorActionPreference = "Stop"

function Parse-DotEnvFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Env file not found: $Path"
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

function Test-IsProbableSecretKey {
    param([string]$Key)
    if ($Key -like "NEXT_PUBLIC_*") { return $false }
    # Browser/client Maps keys belong in frontend env / substitions, not Secret Manager for Cloud Run API.
    if ($Key -eq "GOOGLE_MAPS_API_KEY") { return $false }
    if ($Key -match 'CREDENTIALS|GOOGLE_APPLICATION_CREDENTIALS|ADMIN_CREDENTIALS') { return $false }
    if ($Key -match '^(FIREBASE_PROJECT_ID|GOOGLE_CLOUD_PROJECT|GCP_REGION|GCP_LOCATION|VERTEX_|ACCURACY_|FRONTEND_|TIMER_|DISABLE_|REQUIRE_|ML_|BIGQUERY_|HEATMAP_|SURPLUS_|PUBSUB_|EMERGENCY_|V3_|CORS_|SMTP_HOST|SMTP_PORT|SMTP_USER|SMTP_FROM)$') { return $false }
    if ($Key -match '_SECRET$|_TOKEN$|_API_KEY$|_PASS$') { return $true }
    return $false
}

function Upsert-SecretBlob {
    param([string]$Name, [string]$Value, [string]$ProjectId)
    # Native stderr from "not found" must not stop the script ($ErrorActionPreference = Stop).
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    gcloud secrets describe $Name --project=$ProjectId 2>&1 | Out-Null
    $exists = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev
    if ($exists) {
        Write-Host "Secret versions add: $Name"
        $Value | gcloud secrets versions add $Name --project=$ProjectId --data-file=- | Out-Null
    }
    else {
        Write-Host "Secret create: $Name"
        $Value | gcloud secrets create $Name --project=$ProjectId --data-file=- --replication-policy=automatic | Out-Null
    }
}

function Grant-SecretAccessor {
    param([string]$ProjectId, [string[]]$SecretNames)
    $pn = gcloud projects describe $ProjectId --format="value(projectNumber)"
    if (-not $pn) { throw "Could not resolve project number for $ProjectId" }
    $members = @(
        "serviceAccount:${pn}-compute@developer.gserviceaccount.com",
        "serviceAccount:${pn}@cloudbuild.gserviceaccount.com"
    )
    # gcloud prints IAM updates on stderr; ignore NativeCommandError while bindings succeed.
    $prevEa = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    foreach ($name in $SecretNames) {
        foreach ($m in $members) {
            $null = gcloud secrets add-iam-policy-binding $name `
                --project=$ProjectId `
                --member=$m `
                --role="roles/secretmanager.secretAccessor" `
                --quiet 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Host "(IAM binding may already exist) $name <- $m" -ForegroundColor DarkGray
            }
        }
    }
    $ErrorActionPreference = $prevEa
}

$root = Split-Path -Parent $PSScriptRoot
if (-not $ProjectId) {
    $ProjectId = gcloud config get-value project 2>$null
}
if (-not $ProjectId) {
    throw "Set GCP project: gcloud config set project YOUR_PROJECT_ID"
}

$envPath = $EnvFile
if (-not [System.IO.Path]::IsPathRooted($envPath)) {
    $envPath = Join-Path $root $EnvFile
}

$vars = Parse-DotEnvFile -Path $envPath
# Cloud Run maps TELEGRAM_MASTER_BOT_TOKEN; many .env files use TELEGRAM_BOT_TOKEN only.
if (
    (-not $vars.ContainsKey("TELEGRAM_MASTER_BOT_TOKEN")) -or [string]::IsNullOrWhiteSpace($vars["TELEGRAM_MASTER_BOT_TOKEN"])
) {
    if ($vars.ContainsKey("TELEGRAM_BOT_TOKEN") -and -not [string]::IsNullOrWhiteSpace($vars["TELEGRAM_BOT_TOKEN"])) {
        $vars["TELEGRAM_MASTER_BOT_TOKEN"] = $vars["TELEGRAM_BOT_TOKEN"]
    }
}
$toSync = New-Object System.Collections.Generic.HashSet[string]

foreach ($k in $IncludeKeys) {
    [void]$toSync.Add($k)
}
foreach ($k in $vars.Keys) {
    if (Test-IsProbableSecretKey -Key $k) {
        [void]$toSync.Add($k)
    }
}

$synced = @()
foreach ($name in ($toSync | Sort-Object)) {
    if (-not $vars.ContainsKey($name)) { continue }
    $v = $vars[$name]
    if ([string]::IsNullOrWhiteSpace($v)) { continue }
    if ($v -match '\.(json|pem|p12|pfx)\s*$' -or $v -match '^[A-Za-z]:\\' -or $v -match '^/') {
        Write-Host "Skip $name (looks like a file path, not a secret string)." -ForegroundColor Yellow
        continue
    }
    Upsert-SecretBlob -Name $name -Value $v -ProjectId $ProjectId
    $synced += $name
}

Write-Host "Synced $($synced.Count) secret(s) from $envPath to project $ProjectId." -ForegroundColor Green

if ($GrantIam -and $synced.Count -gt 0) {
    Grant-SecretAccessor -ProjectId $ProjectId -SecretNames $synced
}
