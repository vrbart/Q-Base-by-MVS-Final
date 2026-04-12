# QB Multi-Instance Endpoint Auth Validation Script
# Strict mode: token must come from setup-managed provider config.
# Supported providers:
# - dpapi   : encrypted local token file (default)
# - command : execute local password-manager command that prints token

[CmdletBinding()]
param(
    [string]$ProviderConfigPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-SecretsRoot {
    $localAppData = [string]$env:LOCALAPPDATA
    if (-not [string]::IsNullOrWhiteSpace($localAppData)) {
        return (Join-Path $localAppData "CCBS\secrets")
    }
    $scriptDir = Split-Path -Parent $PSCommandPath
    $repo = Resolve-Path (Join-Path $scriptDir ".")
    return (Join-Path ([string]$repo) ".ccbs\secrets")
}

function Get-DefaultProviderConfigPath {
    $override = [string]$env:CCBS_QB_TOKEN_PROVIDER_FILE
    if (-not [string]::IsNullOrWhiteSpace($override)) {
        return $override
    }
    return (Join-Path (Get-SecretsRoot) "qb_token_provider.json")
}

function Get-DefaultSecureTokenPath {
    $override = [string]$env:CCBS_QB_TOKEN_SECURE_FILE
    if (-not [string]::IsNullOrWhiteSpace($override)) {
        return $override
    }
    return (Join-Path (Get-SecretsRoot) "qb_api_token.dpapi")
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

function Resolve-TokenFromDpapiFile {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Secure token path is empty."
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        throw ("Secure QB token file not found: {0}`nRun setup: powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\set_qb_api_token.ps1" -f $Path)
    }
    $raw = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace([string]$raw)) {
        throw ("Secure QB token file is empty: {0}" -f $Path)
    }
    try {
        $secure = ConvertTo-SecureString -String ([string]$raw).Trim()
        $plain = (Convert-SecureStringToPlainText -Secure $secure).Trim()
        if ([string]::IsNullOrWhiteSpace($plain)) {
            throw "decrypted token is empty"
        }
        return $plain
    } catch {
        throw ("Secure QB token could not be decrypted on this machine/user profile: {0}" -f $Path)
    }
}

function Resolve-TokenFromCommand {
    param([string]$Command)
    $cmdText = ([string]$Command).Trim()
    if ([string]::IsNullOrWhiteSpace($cmdText)) {
        throw "Provider mode 'command' requires token_command in provider config."
    }

    if ($env:ComSpec) {
        $output = & $env:ComSpec /d /s /c $cmdText 2>&1
    } else {
        $output = & bash -lc $cmdText 2>&1
    }
    if ($LASTEXITCODE -ne 0) {
        throw ("Token command failed with exit code {0}. Command: {1}" -f $LASTEXITCODE, $cmdText)
    }

    $line = @($output | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | Select-Object -First 1)
    $token = ([string]($line | Select-Object -First 1)).Trim()
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "Token command produced empty output."
    }
    return $token
}

function Resolve-TokenFromProvider {
    param([string]$ConfigPath)

    if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
        throw "Token provider config path is empty."
    }
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw ("Token provider config not found: {0}`nRun setup: powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\set_qb_api_token.ps1" -f $ConfigPath)
    }

    $raw = Get-Content -LiteralPath $ConfigPath -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace([string]$raw)) {
        throw ("Token provider config is empty: {0}" -f $ConfigPath)
    }

    try {
        $cfg = $raw | ConvertFrom-Json
    } catch {
        throw ("Token provider config is invalid JSON: {0}" -f $ConfigPath)
    }

    $mode = ([string]$cfg.mode).Trim().ToLowerInvariant()
    switch ($mode) {
        "dpapi" {
            $securePath = ([string]$cfg.secure_token_path).Trim()
            if ([string]::IsNullOrWhiteSpace($securePath)) {
                $securePath = Get-DefaultSecureTokenPath
            }
            $token = Resolve-TokenFromDpapiFile -Path $securePath
            return [pscustomobject]@{ token = $token; source = ("provider:dpapi:{0}" -f $securePath) }
        }
        "command" {
            $token = Resolve-TokenFromCommand -Command ([string]$cfg.token_command)
            return [pscustomobject]@{ token = $token; source = "provider:command" }
        }
        default {
            throw ("Unsupported token provider mode '{0}' in {1}. Supported: dpapi, command" -f $mode, $ConfigPath)
        }
    }
}

$providerPath = if ([string]::IsNullOrWhiteSpace($ProviderConfigPath)) { Get-DefaultProviderConfigPath } else { $ProviderConfigPath }
$resolved = Resolve-TokenFromProvider -ConfigPath $providerPath
$token = [string]$resolved.token
Write-Host ("Using token source: {0}" -f [string]$resolved.source)

$baseUrl = "http://127.0.0.1:11435/v3/multi-instance"
$endpoints = @("runtime", "apps", "state", "profile")
$hadFailures = $false

foreach ($ep in $endpoints) {
    $url = "$baseUrl/$ep"
    Write-Host "Checking $url ..."
    try {
        $null = Invoke-RestMethod -Uri $url -Headers @{ Authorization = "Bearer $token" } -Method Get -ErrorAction Stop
        Write-Host "  [$ep] 200 OK"
    } catch {
        Write-Host "  [$ep] FAILED: $($_.Exception.Message)"
        $hadFailures = $true
    }
}

$postUrl = "$baseUrl/profile"
try {
    $null = Invoke-RestMethod -Uri $postUrl -Headers @{ Authorization = "Bearer $token"; 'Content-Type' = 'application/json' } -Method Post -Body '{}' -ErrorAction Stop
    Write-Host "  [POST profile] 200 OK"
} catch {
    Write-Host "  [POST profile] FAILED: $($_.Exception.Message)"
    $hadFailures = $true
}

if ($hadFailures) {
    exit 1
}
exit 0
