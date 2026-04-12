[CmdletBinding()]
param(
  [string]$SubscriptionId = "",
  [string]$ResourceGroup = "",
  [string]$WorkspaceName = "",
  [string]$Location = "",
  [bool]$EnableOwnerAutoAuth = $true,
  [string]$OwnerAutoAuthUser = "demo_owner",
  [switch]$SkipTests,
  [switch]$SkipQuantumChecks,
  [switch]$SkipTokenValidation,
  [switch]$SkipProof,
  [switch]$SkipBrowserInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProofBat = Join-Path $Repo "Q-algofest-proof.bat"
$AutomationDir = Join-Path $Repo "automation"
$CcbsCleanCmd = Join-Path $Repo "ccbs-clean.cmd"

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

$SubscriptionId = Resolve-InputOrEnv -Value $SubscriptionId -EnvName "CCBS_AZ_SUBSCRIPTION_ID"
$ResourceGroup = Resolve-InputOrEnv -Value $ResourceGroup -EnvName "CCBS_AZ_RESOURCE_GROUP"
$WorkspaceName = Resolve-InputOrEnv -Value $WorkspaceName -EnvName "CCBS_AZ_WORKSPACE_NAME"
$Location = Resolve-InputOrEnv -Value $Location -EnvName "CCBS_AZ_LOCATION" -Fallback "eastus"

if (-not (Test-Path -LiteralPath $ProofBat)) {
  throw "Missing proof launcher: $ProofBat"
}
if (-not (Test-Path -LiteralPath $CcbsCleanCmd)) {
  throw "Missing ccbs wrapper: $CcbsCleanCmd"
}

if (-not $SkipProof) {
  Write-Host "[STEP] Running submission smoke proof..." -ForegroundColor Cyan
  $proofArgs = @()
  if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) { $proofArgs += @("-SubscriptionId", $SubscriptionId) }
  if (-not [string]::IsNullOrWhiteSpace($ResourceGroup)) { $proofArgs += @("-ResourceGroup", $ResourceGroup) }
  if (-not [string]::IsNullOrWhiteSpace($WorkspaceName)) { $proofArgs += @("-WorkspaceName", $WorkspaceName) }
  if (-not [string]::IsNullOrWhiteSpace($Location)) { $proofArgs += @("-Location", $Location) }
  if ($SkipTests) { $proofArgs += "-SkipTests" }
  if ($SkipQuantumChecks) { $proofArgs += "-SkipQuantumChecks" }
  if ($SkipTokenValidation) { $proofArgs += "-SkipTokenValidation" }

  & $ProofBat @proofArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Q-algofest-proof.bat failed with exit code $LASTEXITCODE"
  }
}

if ($EnableOwnerAutoAuth) {
  $uname = ([string]$OwnerAutoAuthUser).Trim()
  if ([string]::IsNullOrWhiteSpace($uname)) {
    $uname = "demo_owner"
  }

  Write-Host "[STEP] Enabling owner auto-auth (loopback only)..." -ForegroundColor Cyan
  $pw = [guid]::NewGuid().ToString("n") + "!Aa1"
  & $CcbsCleanCmd ai user create $uname --password $pw --role admin --json | Out-Null
  & $CcbsCleanCmd ai user owner-auth set --username $uname --json | Out-Null
  Write-Host ("[OK] Owner auto-auth enabled for user='{0}' (disable later with: ccbs-clean.cmd ai user owner-auth disable)" -f $uname) -ForegroundColor Green
}

$node = Resolve-Exe -Names @("node")
$npm = Resolve-Exe -Names @("npm", "npm.cmd")
if ([string]::IsNullOrWhiteSpace($node)) {
  throw "Node.js is required for demo capture. Install Node and retry."
}
if ([string]::IsNullOrWhiteSpace($npm)) {
  throw "npm is required for Playwright setup. Install npm and retry."
}
if (-not (Test-Path -LiteralPath $AutomationDir)) {
  throw "Missing automation folder: $AutomationDir"
}

Write-Host "[STEP] Ensuring automation dependencies..." -ForegroundColor Cyan
Push-Location $AutomationDir
try {
  & $npm install
  if ($LASTEXITCODE -ne 0) {
    throw "npm install failed with exit code $LASTEXITCODE"
  }

  if (-not $SkipBrowserInstall) {
    & $npm exec playwright install chromium
    if ($LASTEXITCODE -ne 0) {
      throw "playwright install chromium failed with exit code $LASTEXITCODE"
    }
  }
} finally {
  Pop-Location
}

Write-Host "[DONE] Demo prep complete." -ForegroundColor Green
Write-Host "Next command:"
Write-Host "  .\\Q-demo-record.bat -OpenUi -InstallBrowser"
Write-Host "Canonical demo script: FINAL_QB_DEMO_VIDEO_SCRIPT_AUTOMATION_AI.md"
