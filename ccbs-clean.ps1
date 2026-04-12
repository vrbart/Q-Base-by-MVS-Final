param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvCli = Join-Path $root '.venv-clean\Scripts\ccbs-clean.exe'
$venvPython = Join-Path $root '.venv-clean\Scripts\python.exe'

Push-Location $root
try {
  if (Test-Path -LiteralPath $venvCli) {
    & $venvCli @Args
    exit $LASTEXITCODE
  }

  if (Test-Path -LiteralPath $venvPython) {
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace([string]$env:PYTHONPATH)) {
      'src'
    } else {
      'src' + [IO.Path]::PathSeparator + [string]$env:PYTHONPATH
    }
    & $venvPython -m ccbs_app.cli @Args
    exit $LASTEXITCODE
  }

  $pythonCmd = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($pythonCmd) {
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace([string]$env:PYTHONPATH)) {
      'src'
    } else {
      'src' + [IO.Path]::PathSeparator + [string]$env:PYTHONPATH
    }
    & $pythonCmd.Source -m ccbs_app.cli @Args
    exit $LASTEXITCODE
  }

  throw 'No usable Python launcher found. Expected .venv-clean\Scripts\ccbs-clean.exe or python on PATH.'
} finally {
  Pop-Location
}