param(
  [ValidateSet('status','status-json','watch-status','sync-workspaces','launch','close-lanes','print-config')]
  [string]$Action = 'status',
  [string]$ConfigPath = '',
  [int]$IntervalSec = 5,
  [switch]$ForceRelaunch
)

$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $ConfigPath) {
  $ConfigPath = Join-Path $Repo 'config\codex_instances.json'
}
if (-not (Test-Path -LiteralPath $ConfigPath)) {
  throw "Missing config file: $ConfigPath"
}

function Read-Config([string]$Path) {
  $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  $obj = $raw | ConvertFrom-Json
  if (-not $obj.instances) {
    throw "Config missing instances array: $Path"
  }

  function Expand-PathTemplate([string]$RawPath) {
    $p = ([string]$RawPath).Trim()
    if ([string]::IsNullOrWhiteSpace($p)) {
      return $p
    }

    # Allow portable placeholders inside config files so public repos don't hardcode local user paths.
    $p = $p.Replace('{REPO_ROOT}', $Repo).Replace('${REPO_ROOT}', $Repo).Replace('__REPO_ROOT__', $Repo)
    if ($env:USERPROFILE) {
      $p = $p.Replace('{USERPROFILE}', [string]$env:USERPROFILE).Replace('${USERPROFILE}', [string]$env:USERPROFILE)
    }
    if ($env:HOME) {
      $p = $p.Replace('{HOME}', [string]$env:HOME).Replace('${HOME}', [string]$env:HOME)
    }

    try {
      $p = [Environment]::ExpandEnvironmentVariables($p)
    } catch {
      # ignore
    }

    try {
      if (-not ([System.IO.Path]::IsPathRooted($p))) {
        $p = (Join-Path $Repo $p)
      }
    } catch {
      # ignore
    }

    return $p
  }

  foreach ($inst in @($obj.instances)) {
    if ($null -eq $inst) {
      continue
    }
    try {
      $inst.path = Expand-PathTemplate -RawPath ([string]$inst.path)
    } catch {
      # leave as-is
    }
  }
  return $obj
}

function Get-CcbsCleanCmd {
  $cmdPath = Join-Path $Repo 'ccbs-clean.cmd'
  if (-not (Test-Path -LiteralPath $cmdPath)) {
    throw "Missing ccbs-clean.cmd at $cmdPath"
  }
  return $cmdPath
}

function Get-CliRunner {
  $venvPy = Join-Path $Repo '.venv-clean\Scripts\python.exe'
  if (Test-Path -LiteralPath $venvPy) {
    return [pscustomobject]@{
      Type = 'python'
      Path = $venvPy
    }
  }
  return [pscustomobject]@{
    Type = 'wrapper'
    Path = Get-CcbsCleanCmd
  }
}

function Get-LaneStatePath {
  $stateDir = Join-Path $Repo '.ccbs\state'
  if (-not (Test-Path -LiteralPath $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
  }
  return (Join-Path $stateDir 'codex_multi_lanes.json')
}

function Load-LaneState {
  $path = Get-LaneStatePath
  if (-not (Test-Path -LiteralPath $path)) {
    return @{
      path = $path
      lanes = @{}
    }
  }

  try {
    $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace([string]$raw)) {
      return @{
        path = $path
        lanes = @{}
      }
    }
    $obj = $raw | ConvertFrom-Json
  } catch {
    return @{
      path = $path
      lanes = @{}
    }
  }

  $lanes = @{}
  $src = $obj.lanes
  if ($src) {
    foreach ($p in $src.PSObject.Properties) {
      $name = [string]$p.Name
      $value = $p.Value
      $lanes[$name] = @{
        pid = if ($null -ne $value.pid) { [int]$value.pid } else { 0 }
        name = [string]$value.name
        path = [string]$value.path
        updated_at = [string]$value.updated_at
      }
    }
  }

  return @{
    path = $path
    lanes = $lanes
  }
}

function Save-LaneState {
  param([hashtable]$Lanes)
  $path = Get-LaneStatePath
  $orderedLanes = [ordered]@{}
  foreach ($k in @($Lanes.Keys | Sort-Object)) {
    $row = $Lanes[$k]
    $orderedLanes[$k] = [ordered]@{
      pid = if ($null -ne $row.pid) { [int]$row.pid } else { 0 }
      name = [string]$row.name
      path = [string]$row.path
      updated_at = [string]$row.updated_at
    }
  }
  $payload = [ordered]@{
    version = 'codex-lanes-v1'
    updated_at = [DateTime]::UtcNow.ToString('o')
    lanes = $orderedLanes
  }
  $json = $payload | ConvertTo-Json -Depth 8
  Set-Content -LiteralPath $path -Value $json -Encoding UTF8
}

function Test-ProcessAliveById {
  param([int]$ProcessId)
  if ($ProcessId -le 0) {
    return $false
  }
  try {
    $null = Get-Process -Id $ProcessId -ErrorAction Stop
    return $true
  } catch {
    return $false
  }
}

function Get-ProcessByIdSafe {
  param([int]$ProcessId)
  if ($ProcessId -le 0) {
    return $null
  }
  try {
    return (Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $ProcessId) -ErrorAction SilentlyContinue | Select-Object -First 1)
  } catch {
    return $null
  }
}

function Get-LaneKey {
  param($Instance)
  $instanceId = [string]$Instance.instance_id
  if (-not [string]::IsNullOrWhiteSpace($instanceId)) {
    return $instanceId
  }
  $path = [string]$Instance.path
  if (-not [string]::IsNullOrWhiteSpace($path)) {
    return $path
  }
  return [string]$Instance.name
}

function Normalize-ProcessRecord {
  param($Process)
  if (-not $Process) {
    return $null
  }
  $processId = 0
  try {
    $processId = [int]$Process.ProcessId
  } catch {
    return $null
  }
  if ($processId -le 0) {
    return $null
  }
  return [pscustomobject]@{
    Name = [string]$Process.Name
    ProcessId = $processId
    CommandLine = [string]$Process.CommandLine
  }
}

function Merge-UniqueProcessRecords {
  param([array]$Processes)
  $byProcessId = @{}
  foreach ($proc in @($Processes)) {
    $normalized = Normalize-ProcessRecord -Process $proc
    if (-not $normalized) {
      continue
    }
    $processIdKey = [string]([int]$normalized.ProcessId)
    if (-not $byProcessId.ContainsKey($processIdKey)) {
      $byProcessId[$processIdKey] = $normalized
    }
  }
  return @($byProcessId.Values)
}

function Invoke-Cli {
  param([Alias('Args')] [string[]]$CliArgs)
  $runner = Get-CliRunner
  if ($runner.Type -eq 'python') {
    return (& $runner.Path -m ccbs_app.cli @CliArgs)
  }
  return (& $runner.Path @CliArgs)
}

function Get-WorkspaceState {
  $workspaceJson = Invoke-Cli -CliArgs @('ai', 'workspace', 'list', '--json') 2>$null
  if ([string]::IsNullOrWhiteSpace([string]$workspaceJson)) {
    return [pscustomobject]@{
      Known = @{}
      RegistrationEnforced = $false
    }
  }

  try {
    $workspace = $workspaceJson | ConvertFrom-Json
  } catch {
    return [pscustomobject]@{
      Known = @{}
      RegistrationEnforced = $false
    }
  }
  if (-not $workspace -or -not $workspace.workspaces) {
    return [pscustomobject]@{
      Known = @{}
      RegistrationEnforced = $false
    }
  }

  $known = @{}
  foreach ($row in $workspace.workspaces) {
    if ($row.workspace_id) {
      $known[[string]$row.workspace_id] = $true
    }
  }

  return [pscustomobject]@{
    Known = $known
    RegistrationEnforced = @($workspace.workspaces).Count -gt 0
  }
}

function Get-CodexCommand {
  return Get-Command codex -ErrorAction SilentlyContinue
}

function Get-StatusSnapshot {
  param($Cfg)

  $codex = Get-CodexCommand
  $workspaceState = Get-WorkspaceState
  $known = $workspaceState.Known
  $registrationEnforced = [bool]$workspaceState.RegistrationEnforced
  $laneState = Load-LaneState
  $laneStateLanes = $laneState.lanes

  $total = @($Cfg.instances).Count
  $available = 0
  $rows = @()

  foreach ($instance in $Cfg.instances) {
    $path = [string]$instance.path
    $name = [string]$instance.name
    $workspaceId = [string]$instance.workspace_id
    $exists = Test-Path -LiteralPath $path
    $shells = if ($exists) { Get-ExistingLaneShells -Instance $instance -LaneStateLanes $laneStateLanes } else { @() }
    $shellHealth = if (@($shells).Count -gt 0) { Get-LaneShellHealth -ShellProcesses $shells } else { @() }
    $healthyShellCount = @($shellHealth | Where-Object { [bool]$_.Healthy }).Count
    $registered = if ($registrationEnforced) { $known.ContainsKey($workspaceId) } else { $true }
    $registeredDisplay = if ($registrationEnforced) { [string]$registered } else { 'n/a' }
    $isAvailable = [bool]$codex -and $exists -and $registered
    if ($isAvailable) { $available += 1 }
    $rows += [pscustomobject]@{
      Name = $name
      Workspace = $workspaceId
      PathExists = $exists
      Registered = $registeredDisplay
      LaneShells = @($shells).Count
      HealthyShells = $healthyShellCount
      Available = $isAvailable
    }
  }

  $procCount = @(Get-Process -Name codex -ErrorAction SilentlyContinue).Count
  return [pscustomobject]@{
    config = $ConfigPath
    codex_cli_found = [bool]$codex
    codex_cli = if ($codex) { $codex.Source } else { '' }
    availability_counter = [pscustomobject]@{
      available = $available
      total = $total
      text = ("{0}/{1}" -f $available, $total)
    }
    codex_processes_running = $procCount
    instances = $rows
  }
}

function Show-Status {
  param($Cfg)

  $snapshot = Get-StatusSnapshot -Cfg $Cfg
  Write-Host "Codex multi-instance status"
  Write-Host "- config: $($snapshot.config)"
  Write-Host "- codex_cli_found: $($snapshot.codex_cli_found)"
  if ([string]$snapshot.codex_cli) {
    Write-Host "- codex_cli: $($snapshot.codex_cli)"
  }
  Write-Host ("- availability_counter: {0}" -f $snapshot.availability_counter.text)
  Write-Host ("- codex_processes_running: {0}" -f $snapshot.codex_processes_running)
  @($snapshot.instances) | Format-Table -AutoSize | Out-String -Width 220 | Write-Host
}

function Watch-Status {
  param($Cfg, [int]$IntervalSec)
  if ($IntervalSec -lt 1) {
    $IntervalSec = 1
  }

  while ($true) {
    Clear-Host
    Show-Status -Cfg $Cfg
    Write-Host ("Refreshing in {0}s... (Ctrl+C to stop)" -f $IntervalSec)
    Start-Sleep -Seconds $IntervalSec
  }
}

function Sync-Workspaces {
  param($Cfg)

  $workspaceState = Get-WorkspaceState
  $known = $workspaceState.Known

  foreach ($instance in $Cfg.instances) {
    $workspaceId = [string]$instance.workspace_id
    $name = [string]$instance.name
    if (-not $workspaceId) {
      continue
    }
    if ($known.ContainsKey($workspaceId)) {
      Write-Host "Workspace already exists: $workspaceId"
      continue
    }
    Write-Host "Creating workspace: $workspaceId"
    $null = Invoke-Cli -CliArgs @('ai', 'workspace', 'create', $workspaceId, '--name', $name, '--description', 'Managed by codex_multi_manager', '--json')
  }

  Write-Host "Workspace sync complete."
}

function Start-InstancePowerShell {
  param(
    [string]$Name,
    [string]$Path,
    [string]$LaunchArgs,
    [ValidateSet("Normal","Minimized","Maximized","Hidden")]
    [string]$WindowStyle = ""
  )

  if ([string]::IsNullOrWhiteSpace($WindowStyle)) {
    $WindowStyle = ([string]$env:CCBS_LANE_WINDOW_STYLE).Trim()
  }
  if ([string]::IsNullOrWhiteSpace($WindowStyle)) {
    # Default to hidden to avoid spawning visible windows during automated demos/doctor runs.
    $WindowStyle = "Hidden"
  }

  $safePath = $Path.Replace("'", "''")
  $safeArgs = [string]$LaunchArgs
  $cmd = "$Host.UI.RawUI.WindowTitle = 'CCBS Lane: $Name'; `$env:CCBS_LANE_PATH = '$safePath'; Set-Location -LiteralPath '$safePath'; codex $safeArgs"
  $proc = Start-Process powershell.exe -WindowStyle $WindowStyle -ArgumentList @('-NoProfile','-NoExit','-ExecutionPolicy','Bypass','-Command',$cmd) -PassThru
  $launchedProcessId = if ($proc) { [int]$proc.Id } else { 0 }
  Write-Host "Launched: $Name ($Path)"
  if ($launchedProcessId -gt 0) {
    Write-Host "Lane shell PID: $launchedProcessId"
  }
  return $launchedProcessId
}

function Get-LaneShellProcessesForPath {
  param(
    [string]$Path,
    [string]$Name = ''
  )
  if (-not $Path -and -not $Name) {
    return @()
  }
  $escapedPath = if ($Path) { [regex]::Escape($Path) } else { '' }
  $laneTitle = if ($Name) { "CCBS Lane: $Name" } else { '' }
  $escapedTitle = if ($laneTitle) { [regex]::Escape($laneTitle) } else { '' }

  $fromCmd = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $procName = [string]$_.Name
        $cmd = [string]$_.CommandLine
        if (-not ($procName -ieq 'powershell.exe' -or $procName -ieq 'pwsh.exe')) {
          return $false
        }
        if ([string]::IsNullOrWhiteSpace($cmd)) {
          return $false
        }
        $hasCodex = $cmd -match '(?i)\bcodex(\.cmd|\.exe|\.bat|\.ps1)?\b'
        if (-not $hasCodex) {
          return $false
        }
        $pathMatch = $false
        $titleMatch = $false
        if ($escapedPath) {
          $pathMatch = ($cmd -match $escapedPath)
        }
        if ($escapedTitle) {
          $titleMatch = ($cmd -match $escapedTitle)
        }
        return ($pathMatch -or $titleMatch)
      }
  )

  $fromTitle = @()
  if ($laneTitle) {
    $titleMatches = @(
      Get-Process -ErrorAction SilentlyContinue |
        Where-Object {
          ($_.ProcessName -ieq 'powershell' -or $_.ProcessName -ieq 'pwsh') -and
          ([string]$_.MainWindowTitle -eq $laneTitle)
        }
    )
    foreach ($proc in $titleMatches) {
      if (@($fromCmd | Where-Object { [int]$_.ProcessId -eq [int]$proc.Id }).Count -gt 0) {
        continue
      }
      $cmdLine = ''
      try {
        $cmdLine = [string](Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f [int]$proc.Id) -ErrorAction SilentlyContinue | Select-Object -ExpandProperty CommandLine -First 1)
      } catch {
        $cmdLine = ''
      }
      $fromTitle += [pscustomobject]@{
        Name = ("{0}.exe" -f [string]$proc.ProcessName)
        ProcessId = [int]$proc.Id
        CommandLine = $cmdLine
      }
    }
  }

  $all = @($fromCmd + $fromTitle)
  return (Merge-UniqueProcessRecords -Processes $all)
}

function Get-ExistingLaneShells {
  param(
    $Instance,
    [hashtable]$LaneStateLanes
  )

  $path = [string]$Instance.path
  $name = [string]$Instance.name
  $discovered = @(Get-LaneShellProcessesForPath -Path $path -Name $name)

  $laneKey = Get-LaneKey -Instance $Instance
  if ($LaneStateLanes -and $LaneStateLanes.ContainsKey($laneKey)) {
    $saved = $LaneStateLanes[$laneKey]
    if ($saved) {
      $savedProcessId = 0
      try {
        $savedProcessId = [int]$saved.pid
      } catch {
        $savedProcessId = 0
      }
      if ($savedProcessId -gt 0 -and (Test-ProcessAliveById -ProcessId $savedProcessId)) {
        $savedProc = Get-ProcessByIdSafe -ProcessId $savedProcessId
        if ($savedProc) {
          $discovered += $savedProc
        }
      }
    }
  }

  return (Merge-UniqueProcessRecords -Processes $discovered)
}

function Stop-LaneShellProcesses {
  param([array]$Processes)
  foreach ($proc in @($Processes)) {
    $processId = [int]$proc.ProcessId
    if ($processId -gt 0) {
      try {
        Stop-Process -Id $processId -Force -ErrorAction Stop
        Write-Host "Closed lane shell PID $processId"
      } catch {
        Write-Host "Failed to close lane shell PID ${processId}: $($_.Exception.Message)"
      }
    }
  }
}

function Get-CodexChildrenForShell {
  param([int]$ShellPid)
  if ($ShellPid -le 0) {
    return @()
  }
  return @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        [int]$_.ParentProcessId -eq $ShellPid -and (
          ([string]$_.Name -match '(?i)codex') -or
          ([string]$_.CommandLine -match '(?i)\bcodex(\.cmd|\.exe|\.bat)?\b')
        )
      }
  )
}

function Get-LaneShellHealth {
  param([array]$ShellProcesses)
  $rows = @()
  foreach ($proc in @($ShellProcesses)) {
    $processId = [int]$proc.ProcessId
    $children = Get-CodexChildrenForShell -ShellPid $processId
    $isAlive = Test-ProcessAliveById -ProcessId $processId
    $rows += [pscustomobject]@{
      Shell = $proc
      ProcessId = $processId
      CodexChildren = @($children).Count
      Healthy = $isAlive
    }
  }
  return $rows
}

function Launch-Instances {
  param($Cfg)

  $codex = Get-CodexCommand
  if (-not $codex) {
    throw "codex CLI not found in PATH"
  }

  $laneState = Load-LaneState
  $laneStateLanes = $laneState.lanes

  foreach ($instance in $Cfg.instances) {
    $path = [string]$instance.path
    $name = [string]$instance.name
    $laneKey = Get-LaneKey -Instance $instance
    if (-not (Test-Path -LiteralPath $path)) {
      Write-Host "Skipping missing path: $path"
      if ($laneStateLanes.ContainsKey($laneKey)) {
        $null = $laneStateLanes.Remove($laneKey)
      }
      continue
    }
    $existing = @(Get-ExistingLaneShells -Instance $instance -LaneStateLanes $laneStateLanes)
    if ($existing.Count -gt 1) {
      $extras = @($existing | Select-Object -Skip 1)
      if ($extras.Count -gt 0) {
        Write-Host "Found duplicate lane shells for $name. Closing extras..."
        Stop-LaneShellProcesses -Processes $extras
      }
      $existing = @($existing | Select-Object -First 1)
    }

    if ($ForceRelaunch -and $existing.Count -gt 0) {
      Write-Host "Force relaunch enabled. Restarting lane shell for $name..."
      Stop-LaneShellProcesses -Processes $existing
      $existing = @()
    }

    if ($existing.Count -gt 0) {
      $reusedProcessId = [int]$existing[0].ProcessId
      $laneStateLanes[$laneKey] = @{
        pid = $reusedProcessId
        name = $name
        path = $path
        updated_at = [DateTime]::UtcNow.ToString('o')
      }
      Write-Host "Reusing existing lane shell for $name ($path)"
      continue
    }

    $launchedProcessId = Start-InstancePowerShell -Name $name -Path $path -LaunchArgs ([string]$instance.launch_args)
    if ($launchedProcessId -gt 0) {
      $laneStateLanes[$laneKey] = @{
        pid = [int]$launchedProcessId
        name = $name
        path = $path
        updated_at = [DateTime]::UtcNow.ToString('o')
      }
    }
  }

  Save-LaneState -Lanes $laneStateLanes
  Write-Host "Launch sequence complete."
}

function Close-Lanes {
  param($Cfg)
  $laneState = Load-LaneState
  $laneStateLanes = $laneState.lanes
  foreach ($instance in $Cfg.instances) {
    $path = [string]$instance.path
    $name = [string]$instance.name
    $laneKey = Get-LaneKey -Instance $instance
    $existing = @(Get-ExistingLaneShells -Instance $instance -LaneStateLanes $laneStateLanes)
    if (@($existing).Count -eq 0) {
      Write-Host "No lane shell to close for $name"
      if ($laneStateLanes.ContainsKey($laneKey)) {
        $null = $laneStateLanes.Remove($laneKey)
      }
      continue
    }
    Write-Host "Closing lane shell(s) for $name..."
    Stop-LaneShellProcesses -Processes $existing
    if ($laneStateLanes.ContainsKey($laneKey)) {
      $null = $laneStateLanes.Remove($laneKey)
    }
  }
  Save-LaneState -Lanes $laneStateLanes
  Write-Host "Lane close sequence complete."
}

$cfg = Read-Config -Path $ConfigPath

switch ($Action) {
  'status'          { Show-Status -Cfg $cfg }
  'status-json'     { (Get-StatusSnapshot -Cfg $cfg) | ConvertTo-Json -Depth 8 }
  'watch-status'    { Watch-Status -Cfg $cfg -IntervalSec $IntervalSec }
  'sync-workspaces' { Sync-Workspaces -Cfg $cfg }
  'launch'          { Launch-Instances -Cfg $cfg }
  'close-lanes'     { Close-Lanes -Cfg $cfg }
  'print-config'    { $cfg | ConvertTo-Json -Depth 8 }
}
