[CmdletBinding()]
param(
  [ValidateSet('dpapi','command')]
  [string]$Mode = 'dpapi',
  [string]$TokenCommand = '',
  [string]$SecureTokenPath = '',
  [string]$ProviderConfigPath = '',
  [switch]$Clear,
  [switch]$ShowPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

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

function Convert-SecureStringToPlainText {
  param([System.Security.SecureString]$Secure)
  if ($null -eq $Secure) {
    return ""
  }
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
  try {
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  } finally {
    if ($bstr -ne [IntPtr]::Zero) {
      [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
  }
}

$targetSecurePath = if ([string]::IsNullOrWhiteSpace($SecureTokenPath)) { Get-DefaultSecureTokenPath } else { $SecureTokenPath }
$targetProviderPath = if ([string]::IsNullOrWhiteSpace($ProviderConfigPath)) { Get-DefaultProviderConfigPath } else { $ProviderConfigPath }

if ($ShowPath) {
  Write-Host ("provider_config: {0}" -f $targetProviderPath)
  Write-Host ("secure_token_file: {0}" -f $targetSecurePath)
}

if ($Clear) {
  if (Test-Path -LiteralPath $targetSecurePath) {
    Remove-Item -LiteralPath $targetSecurePath -Force
    Write-Host ("Removed secure QB token file: {0}" -f $targetSecurePath)
  }
  if (Test-Path -LiteralPath $targetProviderPath) {
    Remove-Item -LiteralPath $targetProviderPath -Force
    Write-Host ("Removed token provider config: {0}" -f $targetProviderPath)
  }
  if (-not (Test-Path -LiteralPath $targetSecurePath) -and -not (Test-Path -LiteralPath $targetProviderPath)) {
    Write-Host "No setup files found to clear."
  }
  exit 0
}

$secureParent = Split-Path -Parent $targetSecurePath
if (-not [string]::IsNullOrWhiteSpace($secureParent) -and -not (Test-Path -LiteralPath $secureParent)) {
  New-Item -ItemType Directory -Path $secureParent -Force | Out-Null
}

$providerParent = Split-Path -Parent $targetProviderPath
if (-not [string]::IsNullOrWhiteSpace($providerParent) -and -not (Test-Path -LiteralPath $providerParent)) {
  New-Item -ItemType Directory -Path $providerParent -Force | Out-Null
}

if ($Mode -eq 'dpapi') {
  $first = Read-Host "Enter QB API bearer token" -AsSecureString
  $second = Read-Host "Confirm QB API bearer token" -AsSecureString
  $firstPlain = Convert-SecureStringToPlainText -Secure $first
  $secondPlain = Convert-SecureStringToPlainText -Secure $second
  if ($firstPlain -ne $secondPlain) {
    throw "Token confirmation does not match."
  }
  if ([string]::IsNullOrWhiteSpace([string]$firstPlain)) {
    throw "Token cannot be empty."
  }

  $cipher = ConvertFrom-SecureString -SecureString $first
  Set-Content -LiteralPath $targetSecurePath -Value $cipher -Encoding UTF8

  $provider = [ordered]@{
    mode = 'dpapi'
    secure_token_path = $targetSecurePath
    updated_at = (Get-Date).ToUniversalTime().ToString('o')
  }
  $provider | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $targetProviderPath -Encoding UTF8

  Write-Host ("Saved secure QB token to: {0}" -f $targetSecurePath)
  Write-Host ("Saved token provider config to: {0}" -f $targetProviderPath)
  Write-Host "Token is encrypted for local machine/user profile and is not committed to git."
  exit 0
}

# command mode
$cmdText = ([string]$TokenCommand).Trim()
if ([string]::IsNullOrWhiteSpace($cmdText)) {
  throw "Mode 'command' requires -TokenCommand (your password-manager CLI command that prints only the token)."
}

if ($env:ComSpec) {
  $probe = & $env:ComSpec /d /s /c $cmdText 2>&1
} else {
  $probe = & bash -lc $cmdText 2>&1
}
if ($LASTEXITCODE -ne 0) {
  throw ("Token command probe failed with exit code {0}." -f $LASTEXITCODE)
}
$line = @($probe | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | Select-Object -First 1)
$tokenProbe = ([string]($line | Select-Object -First 1)).Trim()
if ([string]::IsNullOrWhiteSpace($tokenProbe)) {
  throw "Token command probe returned empty output."
}

$provider = [ordered]@{
  mode = 'command'
  token_command = $cmdText
  updated_at = (Get-Date).ToUniversalTime().ToString('o')
}
$provider | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $targetProviderPath -Encoding UTF8

Write-Host ("Saved token provider config to: {0}" -f $targetProviderPath)
Write-Host "Provider mode: command (password-manager CLI)."
Write-Host "No plaintext token stored in repository files."
