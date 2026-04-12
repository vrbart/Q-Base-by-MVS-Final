param(
  [string]$SubscriptionId = "",
  [string]$ResourceGroup = "",
  [string]$WorkspaceName = "",
  [string]$Location = "",
  [switch]$OpenUi,
  [switch]$SkipTests,
  [switch]$SkipQuantumChecks,
  [switch]$SkipTokenValidation,
  [string]$OutputDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DoctorScript = Join-Path $Repo "scripts\qb_doctor.ps1"
$LaneManager = Join-Path $Repo "scripts\codex_multi_manager.ps1"
$ValidateScript = Join-Path $Repo "validate_qb_multi_instance.ps1"
$AzCommand = Get-Command az -ErrorAction SilentlyContinue
if (-not $AzCommand) { $AzCommand = Get-Command az.cmd -ErrorAction SilentlyContinue }

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
  $OutputDir = Join-Path $Repo "dist\algofest\evidence"
}
if (-not (Test-Path -LiteralPath $OutputDir)) {
  New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $DoctorScript)) {
  throw "Missing script: $DoctorScript"
}
if (-not (Test-Path -LiteralPath $LaneManager)) {
  throw "Missing script: $LaneManager"
}

function Resolve-PythonExe {
  $venv = Join-Path $Repo ".venv-clean\Scripts\python.exe"
  if (Test-Path -LiteralPath $venv) { return $venv }
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $cmd3 = Get-Command python3 -ErrorAction SilentlyContinue
  if ($cmd3) { return $cmd3.Source }
  return ""
}

function Get-DefaultSecureTokenPath {
  $override = [string]$env:CCBS_QB_TOKEN_SECURE_FILE
  if (-not [string]::IsNullOrWhiteSpace($override)) {
    return $override
  }
  return (Join-Path (Get-SecretsRoot) "qb_api_token.dpapi")
}

function Get-SecretsRoot {
  $localAppData = [string]$env:LOCALAPPDATA
  if (-not [string]::IsNullOrWhiteSpace($localAppData)) {
    return (Join-Path $localAppData "CCBS\secrets")
  }
  return (Join-Path $Repo ".ccbs\secrets")
}

function Get-DefaultProviderConfigPath {
  $override = [string]$env:CCBS_QB_TOKEN_PROVIDER_FILE
  if (-not [string]::IsNullOrWhiteSpace($override)) {
    return $override
  }
  return (Join-Path (Get-SecretsRoot) "qb_token_provider.json")
}

function Test-HasUsableTokenSource {
  $providerPath = Get-DefaultProviderConfigPath
  if (-not (Test-Path -LiteralPath $providerPath)) { return $false }
  $raw = Get-Content -LiteralPath $providerPath -Raw -ErrorAction SilentlyContinue
  if ([string]::IsNullOrWhiteSpace([string]$raw)) { return $false }
  try {
    $cfg = $raw | ConvertFrom-Json
  } catch {
    return $false
  }
  $mode = ([string]$cfg.mode).Trim().ToLowerInvariant()
  if ($mode -eq "command") {
    return (-not [string]::IsNullOrWhiteSpace(([string]$cfg.token_command).Trim()))
  }
  if ($mode -eq "dpapi") {
    $securePath = ([string]$cfg.secure_token_path).Trim()
    if ([string]::IsNullOrWhiteSpace($securePath)) {
      $securePath = Get-DefaultSecureTokenPath
    }
    if (-not (Test-Path -LiteralPath $securePath)) { return $false }
    $secureRaw = Get-Content -LiteralPath $securePath -Raw -ErrorAction SilentlyContinue
    return (-not [string]::IsNullOrWhiteSpace([string]$secureRaw))
  }
  return $false
}

function Test-ApiHealth {
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:11435/health" -TimeoutSec 3
    return [pscustomobject]@{
      ok = ($resp.StatusCode -eq 200)
      status_code = [int]$resp.StatusCode
    }
  } catch {
    return [pscustomobject]@{
      ok = $false
      status_code = 0
      error = $_.Exception.Message
    }
  }
}

function Get-LaneStatus {
  $raw = & $LaneManager -Action status-json
  if ([string]::IsNullOrWhiteSpace([string]$raw)) {
    throw "Lane status returned empty output."
  }
  return ($raw | ConvertFrom-Json)
}

function Get-QuantumStatus {
  param([bool]$Skip)
  if ($Skip) {
    return [pscustomobject]@{ skipped = $true; reason = "auto_or_flag" }
  }
  $az = Get-Command az -ErrorAction SilentlyContinue
  if (-not $az) {
    return [pscustomobject]@{ skipped = $true; reason = "az_not_found" }
  }
  $raw = & $az.Source quantum workspace show `
    --resource-group $ResourceGroup `
    --workspace-name $WorkspaceName `
    --query "{state:properties.provisioningState,usable:properties.usable,endpoint:properties.endpointUri}" `
    -o json 2>$null
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$raw)) {
    return [pscustomobject]@{ skipped = $true; reason = "workspace_query_failed" }
  }
  return ($raw | ConvertFrom-Json)
}

$doctorParams = @{
  SubscriptionId = $SubscriptionId
  ResourceGroup = $ResourceGroup
  WorkspaceName = $WorkspaceName
  Location = $Location
}
if ($OpenUi) { $doctorParams.OpenUi = $true }

$quantumAutoSkipped = [bool]$SkipQuantumChecks
if (-not $quantumAutoSkipped -and -not $AzCommand) {
  $quantumAutoSkipped = $true
}
if ($quantumAutoSkipped) { $doctorParams.SkipQuantumChecks = $true }

$tokenAutoSkipped = $false
if ($SkipTokenValidation) {
  $tokenAutoSkipped = $true
}
if (-not $tokenAutoSkipped) {
  $tokenAutoSkipped = (-not (Test-HasUsableTokenSource))
}
if ($tokenAutoSkipped) {
  $doctorParams.SkipTokenValidation = $true
}

Write-Host "[STEP] Running QB doctor..."
& $DoctorScript @doctorParams
$doctorExit = $LASTEXITCODE

Write-Host "[STEP] Capturing lane status..."
$lane = Get-LaneStatus

Write-Host "[STEP] Capturing API health..."
$api = Test-ApiHealth

Write-Host "[STEP] Capturing quantum status..."
$quantum = Get-QuantumStatus -Skip $quantumAutoSkipped

$tests = [pscustomobject]@{
  skipped = [bool]$SkipTests
  ok = $true
  exit_code = 0
  command = ""
}
if (-not $SkipTests) {
  $py = Resolve-PythonExe
  if ([string]::IsNullOrWhiteSpace($py)) {
    $tests = [pscustomobject]@{
      skipped = $false
      ok = $false
      exit_code = 127
      command = "python -m pytest -q tests/test_multi_instance_agent.py tests/test_multi_instance_api_surface.py tests/test_ai3_foundry_pane.py"
      error = "python_runtime_not_found"
    }
  } else {
    $testArgs = @(
      "-m", "pytest",
      "-q",
      "tests/test_multi_instance_agent.py",
      "tests/test_multi_instance_api_surface.py",
      "tests/test_ai3_foundry_pane.py"
    )
    Write-Host "[STEP] Running targeted tests..."
    & $py @testArgs
    $testExit = $LASTEXITCODE
    $tests = [pscustomobject]@{
      skipped = $false
      ok = ($testExit -eq 0)
      exit_code = [int]$testExit
      command = (($py + " " + ($testArgs -join " ")).Trim())
    }
  }
}

$laneAvailable = [int]$lane.availability_counter.available
$laneTotal = [int]$lane.availability_counter.total
$allHealthy = (
  ($doctorExit -eq 0) -and
  [bool]$api.ok -and
  ($laneTotal -gt 0 -and $laneAvailable -eq $laneTotal) -and
  [bool]$tests.ok
)

$summary = [ordered]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  command = "scripts/algofest_submission_smoke.ps1"
  doctor_exit_code = [int]$doctorExit
  api = $api
  lanes = [ordered]@{
    availability_counter = [string]$lane.availability_counter.text
    codex_processes_running = [int]$lane.codex_processes_running
    instances = $lane.instances
  }
  quantum = $quantum
  quantum_checks = [ordered]@{
    skipped = [bool]$quantumAutoSkipped
    source = if ($quantumAutoSkipped) { "auto_or_flag" } else { "active" }
  }
  token_validation = [ordered]@{
    skipped = [bool]$tokenAutoSkipped
    source = if ($tokenAutoSkipped) { "auto_or_flag" } else { "active" }
  }
  tests = $tests
  overall_ok = [bool]$allHealthy
}

$outPath = Join-Path $OutputDir "algofest_smoke_summary.json"
$summary | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $outPath -Encoding UTF8

Write-Host ("[DONE] Wrote summary: {0}" -f $outPath)
if (-not $allHealthy) {
  Write-Error "AlgoFest smoke check failed. Review summary JSON."
  exit 1
}
Write-Host "[DONE] AlgoFest smoke check passed."
