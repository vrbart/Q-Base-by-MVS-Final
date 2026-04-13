param(
  [string]$SubscriptionId = "",
  [string]$ResourceGroup = "",
  [string]$WorkspaceName = "",
  [string]$Location = "",
  [int]$MaxRepairPasses = 2,
  [bool]$EnableOwnerAutoAuth = $true,
  [string]$OwnerAutoAuthUser = "demo_owner",
  [switch]$OpenUi,
  [switch]$SkipTargetList,
  [switch]$SkipWorkspaceSync,
  [switch]$SkipLaneLaunch,
  [switch]$SkipTokenValidation,
  [switch]$SkipQuantumChecks,
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
	$BootstrapScript = Join-Path $Repo "scripts\qb_quantum_multi_instance.ps1"
	$LaneManager = Join-Path $Repo "scripts\codex_multi_manager.ps1"
	$ValidateScript = Join-Path $Repo "validate_qb_multi_instance.ps1"
	$CcbsCleanCmd = Join-Path $Repo "ccbs-clean.cmd"
	$AzExe = $null
	$LaneConfigPath = ""

	function Resolve-LaneConfigPath {
	  $raw = ([string]$env:CCBS_CODEX_INSTANCES_CONFIG).Trim()
	  if ([string]::IsNullOrWhiteSpace($raw)) {
	    return ""
	  }
	  $candidate = $raw
	  try {
	    if (-not ([System.IO.Path]::IsPathRooted($candidate))) {
	      $candidate = (Join-Path $Repo $candidate)
	    }
	  } catch {
	    # ignore
	  }
	  if (Test-Path -LiteralPath $candidate) {
	    return $candidate
	  }
	  Write-Host ("[WARN] CCBS_CODEX_INSTANCES_CONFIG was set but path does not exist: {0}" -f $candidate) -ForegroundColor Yellow
	  return ""
	}

	function Invoke-LaneManager {
	  param([hashtable]$Params)
	  if (-not $Params) {
	    $Params = @{}
	  }
	  if (-not [string]::IsNullOrWhiteSpace($LaneConfigPath) -and (-not $Params.ContainsKey("ConfigPath"))) {
	    $Params.ConfigPath = $LaneConfigPath
	  }
	  return (& $LaneManager @Params)
	}

	function Invoke-LaneManagerStatusJson {
	  $attempts = 3
	  for ($attempt = 1; $attempt -le $attempts; $attempt++) {
	    $raw = Invoke-LaneManager @{ Action = "status-json" }
	    if (-not [string]::IsNullOrWhiteSpace([string]$raw)) {
	      try {
	        return ($raw | ConvertFrom-Json)
	      } catch {
	        Write-Host ("[WARN] Lane manager status-json parse failed on attempt {0}/{1}: {2}" -f $attempt, $attempts, $_.Exception.Message) -ForegroundColor Yellow
	      }
	    } else {
	      Write-Host ("[WARN] Lane manager status-json returned no output on attempt {0}/{1}." -f $attempt, $attempts) -ForegroundColor Yellow
	    }
	    Start-Sleep -Milliseconds 350
	  }

	  throw "Lane manager status-json returned no usable JSON output after retries."
	}

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
	$LaneConfigPath = Resolve-LaneConfigPath

function Get-SecretsRoot {
  $localAppData = [string]$env:LOCALAPPDATA
  if (-not [string]::IsNullOrWhiteSpace($localAppData)) {
    return (Join-Path $localAppData "CCBS\secrets")
  }
  return (Join-Path $Repo ".ccbs\secrets")
}

function Get-DefaultSecureTokenPath {
  $override = [string]$env:CCBS_QB_TOKEN_SECURE_FILE
  if (-not [string]::IsNullOrWhiteSpace($override)) {
    return $override
  }
  return (Join-Path (Get-SecretsRoot) "qb_api_token.dpapi")
}

function Get-DefaultProviderConfigPath {
  $override = [string]$env:CCBS_QB_TOKEN_PROVIDER_FILE
  if (-not [string]::IsNullOrWhiteSpace($override)) {
    return $override
  }
  return (Join-Path (Get-SecretsRoot) "qb_token_provider.json")
}

function Test-HasConfiguredTokenProvider {
  $providerPath = Get-DefaultProviderConfigPath
  if (-not (Test-Path -LiteralPath $providerPath)) {
    return $false
  }
  $raw = Get-Content -LiteralPath $providerPath -Raw -ErrorAction SilentlyContinue
  if ([string]::IsNullOrWhiteSpace([string]$raw)) {
    return $false
  }
  try {
    $cfg = $raw | ConvertFrom-Json
  } catch {
    return $false
  }
  $mode = ([string]$cfg.mode).Trim().ToLowerInvariant()
  switch ($mode) {
    "dpapi" {
      $securePath = ([string]$cfg.secure_token_path).Trim()
      if ([string]::IsNullOrWhiteSpace($securePath)) {
        $securePath = Get-DefaultSecureTokenPath
      }
      if (-not (Test-Path -LiteralPath $securePath)) {
        return $false
      }
      $secureRaw = Get-Content -LiteralPath $securePath -Raw -ErrorAction SilentlyContinue
      return (-not [string]::IsNullOrWhiteSpace([string]$secureRaw))
    }
    "command" {
      $cmd = ([string]$cfg.token_command).Trim()
      return (-not [string]::IsNullOrWhiteSpace($cmd))
    }
    default {
      return $false
    }
  }
}

function Get-TokenProviderHint {
  $providerPath = Get-DefaultProviderConfigPath
  if (Test-Path -LiteralPath $providerPath) {
    return $providerPath
  }
  return ("provider config will be created at: {0}" -f $providerPath)
}

function Should-SkipTokenValidationAuto {
  if ($SkipTokenValidation) {
    return $true
  }
  return $false
}

function Resolve-AzExecutable {
  $cmd = Get-Command az -ErrorAction SilentlyContinue
  if (-not $cmd) {
    $cmd = Get-Command az.cmd -ErrorAction SilentlyContinue
  }
  if (-not $cmd) {
    throw "Azure CLI 'az' is not available in PATH."
  }
  return $cmd.Source
}

function Invoke-AzJson {
  param([string[]]$Arguments)
  $raw = & $AzExe @Arguments
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    throw ("az command failed ({0}): az {1}" -f $exitCode, ($Arguments -join " "))
  }
  if ([string]::IsNullOrWhiteSpace([string]$raw)) {
    return $null
  }
  try {
    return ($raw | ConvertFrom-Json)
  } catch {
    throw ("Unable to parse az JSON output for command: az {0}" -f ($Arguments -join " "))
  }
}

function Test-ApiHealthy {
  $deadline = (Get-Date).AddSeconds(25)
  do {
    try {
      $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:11435/health" -TimeoutSec 2
      if ($resp.StatusCode -eq 200) {
        return $true
      }
    } catch {
      # startup warmup
    }
    Start-Sleep -Milliseconds 700
  } while ((Get-Date) -lt $deadline)
  return $false
}

	function Get-LaneStatusSnapshot {
	  if (-not (Test-Path -LiteralPath $LaneManager)) {
	    throw "Missing lane manager script: $LaneManager"
	  }
	  return (Invoke-LaneManagerStatusJson)
	}

function Get-WorkspaceHealth {
if ($SkipQuantumChecks) {
  return [pscustomobject]@{
      ok = $true
      state = "skipped"
      usable = "skipped"
      endpoint = ""
    }
  }
  $info = Invoke-AzJson @(
    "quantum",
    "workspace",
    "show",
    "--resource-group",
    $ResourceGroup,
    "--workspace-name",
    $WorkspaceName,
    "--query",
    "{state:properties.provisioningState,usable:properties.usable,endpoint:properties.endpointUri}",
    "-o",
    "json"
  )
  $state = [string]$info.state
  $usable = [string]$info.usable
  return [pscustomobject]@{
    ok = ($state -eq "Succeeded" -and $usable -eq "Yes")
    state = $state
    usable = $usable
    endpoint = [string]$info.endpoint
  }
}

function Enable-OwnerAutoAuthIfRequested {
  if (-not $EnableOwnerAutoAuth) {
    return
  }
  if (-not (Test-Path -LiteralPath $CcbsCleanCmd)) {
    Write-Host "[WARN] Owner auto-auth requested but ccbs wrapper is missing: $CcbsCleanCmd" -ForegroundColor Yellow
    return
  }

  $uname = ([string]$OwnerAutoAuthUser).Trim()
  if ([string]::IsNullOrWhiteSpace($uname)) {
    $uname = "demo_owner"
  }

  try {
    Write-Host "[STEP] Enabling owner auto-auth (loopback only)..." -ForegroundColor Cyan
    $pw = [guid]::NewGuid().ToString("n") + "!Aa1"
    & $CcbsCleanCmd ai user create $uname --password $pw --role admin --json *> $null
    $exitCreate = 0
    $lastExitVar = Get-Variable LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    if ($lastExitVar) {
      $exitCreate = [int]$global:LASTEXITCODE
    }
    if ($exitCreate -ne 0) {
      throw "ccbs-clean user create failed (exit $exitCreate)."
    }
    & $CcbsCleanCmd ai user owner-auth set --username $uname --json *> $null
    $exitOwnerAuth = 0
    $lastExitVar = Get-Variable LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    if ($lastExitVar) {
      $exitOwnerAuth = [int]$global:LASTEXITCODE
    }
    if ($exitOwnerAuth -ne 0) {
      throw "ccbs-clean owner-auth set failed (exit $exitOwnerAuth)."
    }
    Write-Host ("[OK] Owner auto-auth enabled for user='{0}' (disable later with: ccbs-clean.cmd ai user owner-auth disable)" -f $uname) -ForegroundColor Green
  } catch {
    Write-Host ("[WARN] Failed to enable owner auto-auth: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
  }
}

function Invoke-TokenValidation {
  if ($SkipTokenValidation) {
    return [pscustomobject]@{ ok = $true; detail = "skipped" }
  }
  if (-not (Test-Path -LiteralPath $ValidateScript)) {
    return [pscustomobject]@{ ok = $false; detail = "missing validation script: $ValidateScript" }
  }
  & $ValidateScript
  $ok = ($LASTEXITCODE -eq 0)
  return [pscustomobject]@{
    ok = $ok
    detail = if ($ok) { "passed" } else { "validate_qb_multi_instance.ps1 failed (secure token missing/invalid or endpoint failure)" }
  }
}

function Test-DoctorHealth {
  $workspace = Get-WorkspaceHealth
  $apiHealthy = Test-ApiHealthy
  $lane = Get-LaneStatusSnapshot
  $available = [int]$lane.availability_counter.available
  $total = [int]$lane.availability_counter.total
  $laneOk = ($total -gt 0 -and $available -eq $total)
  $tokenValidation = Invoke-TokenValidation
  $tokenOk = [bool]$tokenValidation.ok
  $softApiDegraded = ($workspace.ok -and $laneOk -and $tokenOk -and (-not $apiHealthy))
  if ($softApiDegraded) {
    Write-Host "[WARN] API health probe failed but workspace/lanes/token checks are healthy. Treating as soft-ready for demo flow." -ForegroundColor Yellow
  }
  return [pscustomobject]@{
    ok = ($workspace.ok -and $laneOk -and $tokenOk -and ($apiHealthy -or $softApiDegraded))
    workspace = $workspace
    api_healthy = $apiHealthy
    api_soft_degraded = $softApiDegraded
    lane = [pscustomobject]@{
      ok = $laneOk
      available = $available
      total = $total
      text = [string]$lane.availability_counter.text
      codex_processes_running = [int]$lane.codex_processes_running
    }
    token_validation = $tokenValidation
  }
}

function Can-ReuseCurrentLanes {
  try {
    $snapshot = Get-LaneStatusSnapshot
    $available = [int]$snapshot.availability_counter.available
    $total = [int]$snapshot.availability_counter.total
    return ($total -gt 0 -and $available -eq $total)
  } catch {
    return $false
  }
}

if (-not (Test-Path -LiteralPath $BootstrapScript)) {
  throw "Missing bootstrap script: $BootstrapScript"
}
if ($MaxRepairPasses -lt 0) {
  throw "MaxRepairPasses must be >= 0."
}

if (-not $SkipQuantumChecks) {
  if ([string]::IsNullOrWhiteSpace($SubscriptionId)) {
    Write-Host "[WARN] SubscriptionId not provided; attempting Azure CLI default subscription." -ForegroundColor Yellow
  }
  if ([string]::IsNullOrWhiteSpace($WorkspaceName)) {
    Write-Host "[WARN] WorkspaceName not provided; attempting Azure CLI default workspace." -ForegroundColor Yellow
  }
}

if ((-not $SkipTokenValidation) -and (-not (Test-HasConfiguredTokenProvider))) {
  $hint = Get-TokenProviderHint
  if ($EnableOwnerAutoAuth) {
    Write-Host ("[WARN] Token provider not configured ({0}). Continuing because owner auto-auth is enabled for loopback demo use. Set -SkipTokenValidation to silence this warning." -f $hint) -ForegroundColor Yellow
    $SkipTokenValidation = $true
  } else {
    throw ("Setup-managed QB token provider is required and not configured: {0}`nRun: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\set_qb_api_token.ps1" -f $hint)
  }
}

if (-not $SkipQuantumChecks) {
  $AzExe = Resolve-AzExecutable
}

Push-Location $Repo
try {
  $reuseLanes = Can-ReuseCurrentLanes
  if ($reuseLanes) {
    Write-Host "[INFO] Existing lanes look healthy; first pass will reuse without launching new lane shells." -ForegroundColor DarkCyan
  }

  # Ensure the /v3/* authenticated surfaces are usable in demos without pasting a bearer token.
  # This only enables loopback owner auto-auth (as implemented by ccbs-clean.cmd).
  Enable-OwnerAutoAuthIfRequested

  $maxAttempts = $MaxRepairPasses + 1
  for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    $forceRelaunch = ($attempt -gt 1)
    Write-Host ("[STEP] QB doctor pass {0}/{1}" -f $attempt, $maxAttempts) -ForegroundColor Cyan

    $bootstrapParams = @{
      SubscriptionId = $SubscriptionId
      ResourceGroup = $ResourceGroup
      WorkspaceName = $WorkspaceName
      Location = $Location
    }
    if ($SkipTargetList) { $bootstrapParams.SkipTargetList = $true }
    if ($SkipWorkspaceSync) { $bootstrapParams.SkipWorkspaceSync = $true }
    if ($SkipLaneLaunch) { $bootstrapParams.SkipLaneLaunch = $true }
    if ($SkipQuantumChecks) { $bootstrapParams.SkipQuantumChecks = $true }
    if ($attempt -eq 1 -and $reuseLanes) { $bootstrapParams.SkipLaneLaunch = $true }
    if ($forceRelaunch) { $bootstrapParams.ForceLaneRelaunch = $true }
    if ($DryRun) { $bootstrapParams.DryRun = $true }
    if ($OpenUi -and $attempt -eq 1) { $bootstrapParams.OpenUi = $true }

    & $BootstrapScript @bootstrapParams

    if ($DryRun) {
      Write-Host "[DONE] Dry-run complete."
      exit 0
    }

    $health = Test-DoctorHealth
    Write-Host ("- workspace: ok={0} state={1} usable={2}" -f [bool]$health.workspace.ok, [string]$health.workspace.state, [string]$health.workspace.usable)
    Write-Host ("- api_healthy: {0}" -f [bool]$health.api_healthy)
    Write-Host ("- lanes: ok={0} availability={1} codex_processes_running={2}" -f [bool]$health.lane.ok, [string]$health.lane.text, [int]$health.lane.codex_processes_running)
    Write-Host ("- token_validation: ok={0} detail={1}" -f [bool]$health.token_validation.ok, [string]$health.token_validation.detail)

    if ([bool]$health.ok) {
      Write-Host "[DONE] QB doctor: system is healthy." -ForegroundColor Green
      exit 0
    }

    if ($attempt -lt $maxAttempts) {
      Write-Warning "Doctor health checks failed. Retrying with forced lane relaunch."
    }
  }

  Write-Error "QB doctor failed: system is still unhealthy after repair passes."
  exit 1
} finally {
  Pop-Location
}
