param(
  [string]$SubscriptionId = "",
  [string]$ResourceGroup = "",
  [string]$WorkspaceName = "",
  [string]$Location = "",
  [switch]$SkipQuantumChecks,
  [switch]$SkipTargetList,
  [switch]$SkipWorkspaceSync,
  [switch]$SkipLaneLaunch,
  [switch]$ForceLaneRelaunch,
  [switch]$SkipApi,
  [switch]$OpenUi,
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

	$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
	$LaneManager = Join-Path $Repo "scripts\codex_multi_manager.ps1"
	$QLaunch = Join-Path $Repo "Q-launch.bat"
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
	  param([string[]]$Args)
	  if ([string]::IsNullOrWhiteSpace($LaneConfigPath)) {
	    return (& $LaneManager @Args)
	  }
	  return (& $LaneManager -ConfigPath $LaneConfigPath @Args)
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

function Run-Step {
  param(
    [string]$Label,
    [scriptblock]$Action
  )
  Write-Host ("[STEP] {0}" -f $Label) -ForegroundColor Cyan
  if ($DryRun) {
    Write-Host "       (dry-run: skipped)"
    return
  }
  & $Action
}

function Invoke-AzChecked {
  param([string[]]$Arguments)
  & $AzExe @Arguments
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    throw ("az command failed ({0}): az {1}" -f $exitCode, ($Arguments -join " "))
  }
}

	function Get-LaneStatusSnapshotSafe {
	  if (-not (Test-Path -LiteralPath $LaneManager)) {
	    return $null
	  }
	  try {
	    $raw = Invoke-LaneManager @("-Action", "status-json") 2>$null
	    if ([string]::IsNullOrWhiteSpace([string]$raw)) {
	      return $null
	    }
	    return ($raw | ConvertFrom-Json)
	  } catch {
	    return $null
	  }
	}

	$SubscriptionId = Resolve-InputOrEnv -Value $SubscriptionId -EnvName "CCBS_AZ_SUBSCRIPTION_ID"
	$ResourceGroup = Resolve-InputOrEnv -Value $ResourceGroup -EnvName "CCBS_AZ_RESOURCE_GROUP" -Fallback "CCBS"
	$WorkspaceName = Resolve-InputOrEnv -Value $WorkspaceName -EnvName "CCBS_AZ_WORKSPACE_NAME"
	$Location = Resolve-InputOrEnv -Value $Location -EnvName "CCBS_AZ_LOCATION" -Fallback "eastus"
	$LaneConfigPath = Resolve-LaneConfigPath

if (-not $SkipQuantumChecks) {
  $azCommand = Get-Command az -ErrorAction SilentlyContinue
  if (-not $azCommand) {
    $azCommand = Get-Command az.cmd -ErrorAction SilentlyContinue
  }
  if (-not $azCommand) {
    throw "Azure CLI 'az' is not available in PATH."
  }
  $AzExe = $azCommand.Source

  if ([string]::IsNullOrWhiteSpace($SubscriptionId)) {
    $detectedSub = [string](& $AzExe account show --query id -o tsv 2>$null)
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($detectedSub)) {
      $SubscriptionId = $detectedSub.Trim()
    }
  }

  if ([string]::IsNullOrWhiteSpace($WorkspaceName) -or [string]::IsNullOrWhiteSpace($ResourceGroup)) {
    $wsRaw = [string](& $AzExe quantum workspace show --query "{name:name,resourceGroup:resourceGroup}" -o json 2>$null)
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($wsRaw)) {
      try {
        $wsDefault = $wsRaw | ConvertFrom-Json
        if ([string]::IsNullOrWhiteSpace($WorkspaceName)) {
          $WorkspaceName = ([string]$wsDefault.name).Trim()
        }
        if ([string]::IsNullOrWhiteSpace($ResourceGroup)) {
          $ResourceGroup = ([string]$wsDefault.resourceGroup).Trim()
        }
      } catch {
        # Ignore parsing issues; explicit validation below will surface actionable errors.
      }
    }
  }
}

if (-not (Test-Path -LiteralPath $LaneManager)) {
  throw "Missing lane manager script: $LaneManager"
}
if (-not (Test-Path -LiteralPath $QLaunch)) {
  throw "Missing launcher: $QLaunch"
}
if (-not $SkipQuantumChecks) {
  if ([string]::IsNullOrWhiteSpace($SubscriptionId)) {
    throw "SubscriptionId is required. Pass -SubscriptionId or set CCBS_AZ_SUBSCRIPTION_ID."
  }
  if ([string]::IsNullOrWhiteSpace($ResourceGroup)) {
    throw "ResourceGroup is required. Pass -ResourceGroup or set CCBS_AZ_RESOURCE_GROUP."
  }
  if ([string]::IsNullOrWhiteSpace($WorkspaceName)) {
    throw "WorkspaceName is required. Pass -WorkspaceName or set CCBS_AZ_WORKSPACE_NAME."
  }
}

Push-Location $Repo
try {
  if ($SkipQuantumChecks) {
    Write-Host "[INFO] Azure Quantum checks skipped." -ForegroundColor DarkCyan
  } else {
    Run-Step -Label "Set Azure subscription" -Action {
      Invoke-AzChecked @("account", "set", "--subscription", $SubscriptionId) | Out-Null
    }

    Run-Step -Label "Bind active Azure Quantum workspace" -Action {
      try {
        Invoke-AzChecked @("quantum", "workspace", "set", "--resource-group", $ResourceGroup, "--workspace-name", $WorkspaceName) | Out-Null
      } catch {
        if ([string]::IsNullOrWhiteSpace($Location)) {
          throw
        }
        # Backward compatibility with older extension variants.
        Invoke-AzChecked @("quantum", "workspace", "set", "--resource-group", $ResourceGroup, "--workspace-name", $WorkspaceName, "--location", $Location) | Out-Null
      }
    }

    Run-Step -Label "Show active workspace status" -Action {
      Invoke-AzChecked @("quantum", "workspace", "show", "--resource-group", $ResourceGroup, "--workspace-name", $WorkspaceName, "--query", "{state:properties.provisioningState,usable:properties.usable,endpoint:properties.endpointUri,storage:properties.storageAccount}", "-o", "jsonc")
    }

    if (-not $SkipTargetList) {
      Run-Step -Label "List Azure Quantum targets" -Action {
        Invoke-AzChecked @("quantum", "target", "list", "-o", "table")
      }
    }
  }

  if (-not $SkipApi) {
    Run-Step -Label "Start QB API stack (without lane relaunch)" -Action {
      $env:Q_LAUNCH_SKIP_LANES = "1"
      if ($OpenUi) {
        Remove-Item Env:Q_LAUNCH_SKIP_BROWSER -ErrorAction SilentlyContinue
      } else {
        $env:Q_LAUNCH_SKIP_BROWSER = "1"
      }
      try {
        & $QLaunch
      } finally {
        Remove-Item Env:Q_LAUNCH_SKIP_LANES -ErrorAction SilentlyContinue
        Remove-Item Env:Q_LAUNCH_SKIP_BROWSER -ErrorAction SilentlyContinue
      }
    }
  }

  if (-not $SkipLaneLaunch) {
		  if (-not $SkipWorkspaceSync) {
		    Run-Step -Label "Sync multi-instance workspace registry" -Action {
		      Invoke-LaneManager @("-Action", "sync-workspaces")
		    }
		  }

    $laneSnapshot = Get-LaneStatusSnapshotSafe
    $skipLaneLaunchBecauseHealthy = $false
    if (-not $ForceLaneRelaunch -and $laneSnapshot) {
      $available = [int]$laneSnapshot.availability_counter.available
      $total = [int]$laneSnapshot.availability_counter.total
      $running = [int]$laneSnapshot.codex_processes_running
      $healthyShells = 0
      foreach ($row in @($laneSnapshot.instances)) {
        $healthyShells += [int]$row.HealthyShells
      }
      $laneWindows = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.ProcessName -ieq "powershell" -or $_.ProcessName -ieq "pwsh") -and
        ([string]$_.MainWindowTitle -like "CCBS Lane:*")
      }).Count
      if ($total -gt 0 -and $available -eq $total -and ($running -ge $total -or $healthyShells -ge $total -or $laneWindows -ge $total)) {
        $skipLaneLaunchBecauseHealthy = $true
        Write-Host ("[INFO] Existing lane activity detected (codex={0}, healthy_shells={1}, lane_windows={2}); skipping lane spawn to avoid window spam." -f $running, $healthyShells, $laneWindows) -ForegroundColor DarkCyan
      }
    }
		    if (-not $skipLaneLaunchBecauseHealthy -or $ForceLaneRelaunch) {
		      Run-Step -Label "Launch/reuse QB multi-instance lanes" -Action {
		        if ($ForceLaneRelaunch) {
		          Invoke-LaneManager @("-Action", "launch", "-ForceRelaunch")
		        } else {
		          Invoke-LaneManager @("-Action", "launch")
		        }
		      }
		    } else {
      Write-Host "[STEP] Launch/reuse QB multi-instance lanes"
      Write-Host "       (skipped: healthy lane set already running)"
    }

		    Run-Step -Label "Verify lane health" -Action {
		      Invoke-LaneManager @("-Action", "status")
		    }
		  }

  Write-Host "[DONE] QB quantum + multi-instance bootstrap complete." -ForegroundColor Green
} finally {
  Pop-Location
}
