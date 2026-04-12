[CmdletBinding()]
param(
  [string]$SubscriptionId = "",
  [string]$ResourceGroup = "",
  [string]$WorkspaceName = "",
  [string]$Location = "",
  [string]$UiUrl = "http://127.0.0.1:11435/v3/ui",
  [string]$HealthUrl = "http://127.0.0.1:11435/health",
  [string]$OutputDir = "",
  [string]$Prompt = "Build a simple team productivity web app (auth + todo CRUD + docs + deploy). Decompose and assign across 3 lanes; show optimizer decision + evidence",
  [int]$CaptureSeconds = 260,
  [switch]$SkipDoctor,
  [switch]$SkipQuantumChecks,
  [switch]$SkipTokenValidation,
  [switch]$InstallBrowser,
  [switch]$Headed,
  [switch]$OpenUi
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DoctorBat = Join-Path $Repo "QB-doctor.bat"
$AutomationDir = Join-Path $Repo "automation"
$CaptureScript = Join-Path $AutomationDir "capture_ui_demo.mjs"

function Resolve-InputOrEnv {
  param(
    [string]$Value,
    [string]$EnvName,
    [string]$Fallback = ""
  )
  $trimmed = ([string]$Value).Trim()
  if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
    return $trimmed
  }
  $rawEnvValue = [Environment]::GetEnvironmentVariable($EnvName)
  $envValue = ([string]$rawEnvValue).Trim()
  if (-not [string]::IsNullOrWhiteSpace($envValue)) {
    return $envValue
  }
  return $Fallback
}

$SubscriptionId = Resolve-InputOrEnv -Value $SubscriptionId -EnvName "CCBS_AZ_SUBSCRIPTION_ID"
$ResourceGroup = Resolve-InputOrEnv -Value $ResourceGroup -EnvName "CCBS_AZ_RESOURCE_GROUP" -Fallback "CCBS"
$WorkspaceName = Resolve-InputOrEnv -Value $WorkspaceName -EnvName "CCBS_AZ_WORKSPACE_NAME"
$Location = Resolve-InputOrEnv -Value $Location -EnvName "CCBS_AZ_LOCATION" -Fallback "eastus"

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  $OutputDir = Join-Path $Repo "dist\demo"
}

if (-not (Test-Path -LiteralPath $DoctorBat)) {
  throw "Missing doctor launcher: $DoctorBat"
}
if (-not (Test-Path -LiteralPath $CaptureScript)) {
  throw "Missing capture script: $CaptureScript"
}

if (-not (Test-Path -LiteralPath $OutputDir)) {
  New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

function Resolve-Exe {
  param([string[]]$Names)
  foreach ($name in $Names) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
      return $cmd.Source
    }
  }
  return ""
}

function Wait-Http200 {
  param(
    [string]$Url,
    [int]$TimeoutSec = 90
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  do {
    try {
      $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
      if ($resp.StatusCode -eq 200) {
        return $true
      }
    } catch {
      Start-Sleep -Milliseconds 800
    }
  } while ((Get-Date) -lt $deadline)

  return $false
}

$node = Resolve-Exe -Names @("node")
$npm = Resolve-Exe -Names @("npm", "npm.cmd")
if ([string]::IsNullOrWhiteSpace($node)) {
  throw "Node.js is required for Playwright capture (node not found in PATH)."
}
if ([string]::IsNullOrWhiteSpace($npm)) {
  throw "npm is required for Playwright setup (npm not found in PATH)."
}

Push-Location $Repo
try {
  if (-not $SkipDoctor) {
    Write-Host "[STEP] Running QB doctor/bootstrap..." -ForegroundColor Cyan
    $doctorArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) { $doctorArgs += @("-SubscriptionId", $SubscriptionId) }
    if (-not [string]::IsNullOrWhiteSpace($ResourceGroup)) { $doctorArgs += @("-ResourceGroup", $ResourceGroup) }
    if (-not [string]::IsNullOrWhiteSpace($WorkspaceName)) { $doctorArgs += @("-WorkspaceName", $WorkspaceName) }
    if (-not [string]::IsNullOrWhiteSpace($Location)) { $doctorArgs += @("-Location", $Location) }
    if ($OpenUi) { $doctorArgs += "-OpenUi" }
    if ($SkipQuantumChecks) { $doctorArgs += "-SkipQuantumChecks" }
    if ($SkipTokenValidation) { $doctorArgs += "-SkipTokenValidation" }

    & $DoctorBat @doctorArgs
    if ($LASTEXITCODE -ne 0) {
      throw "QB-doctor failed with exit code $LASTEXITCODE"
    }
  }

  Write-Host "[STEP] Waiting for QB API health endpoint..." -ForegroundColor Cyan
  if (-not (Wait-Http200 -Url $HealthUrl -TimeoutSec 120)) {
    throw "API health endpoint did not return 200 in time: $HealthUrl"
  }
  Write-Host "[OK] API healthy at $HealthUrl" -ForegroundColor Green

  Write-Host "[STEP] Ensuring Playwright automation dependencies..." -ForegroundColor Cyan
  Push-Location $AutomationDir
  try {
    if (-not (Test-Path -LiteralPath (Join-Path $AutomationDir "node_modules\playwright"))) {
      & $npm install
      if ($LASTEXITCODE -ne 0) {
        throw "npm install failed with exit code $LASTEXITCODE"
      }
    }

    if ($InstallBrowser) {
      & $npm exec playwright install chromium
      if ($LASTEXITCODE -ne 0) {
        throw "playwright install chromium failed with exit code $LASTEXITCODE"
      }
    }
  } finally {
    Pop-Location
  }

  Write-Host "[STEP] Capturing UI demo with Playwright..." -ForegroundColor Cyan
	  $nodeArgs = @(
	    $CaptureScript,
	    "--url", $UiUrl,
	    "--output-dir", $OutputDir,
	    "--prompt", $Prompt,
	    "--duration-sec", [string]$CaptureSeconds,
	    "--pace-ms", "650",
	    "--hold-ms", "900",
	    "--target-actions", "200",
	    "--cycles", "120",
	    "--end-buffer-ms", "9000"
	  )
  if ($Headed) {
    $nodeArgs += "--headed"
  }

  & $node @nodeArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Playwright capture failed with exit code $LASTEXITCODE"
  }

  Write-Host "[DONE] Demo automation complete." -ForegroundColor Green
  Write-Host "       Output directory: $OutputDir"
} finally {
  Pop-Location
}
