param(
    [Alias("install-mamba")]
    [switch]$InstallMamba,

    [Alias("install-core")]
    [switch]$InstallCore,

    [Alias("yes")]
    [switch]$Yes,

    [Alias("continue-on-error")]
    [switch]$ContinueOnError,

    [Alias("write-handoff")]
    [switch]$WriteHandoff,

    [Alias("analyze-nondeterministic")]
    [switch]$AnalyzeNondeterministic,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$BootstrapArgs
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

$isWindows = $env:OS -eq "Windows_NT"
if ($PSVersionTable.PSEdition -eq "Core") {
    $isWindows = $IsWindows
}
if (-not $isWindows) {
    throw "Unsupported OS for this bootstrap script. Use DEPENDENCY/bootstrap.sh on Linux or macOS."
}

function Add-UvPaths {
    $homeDir = [Environment]::GetFolderPath("UserProfile")
    $candidates = @(
        (Join-Path $homeDir ".local\bin"),
        (Join-Path $homeDir ".cargo\bin")
    )
    foreach ($candidate in $candidates) {
        if ((Test-Path $candidate) -and (($env:PATH -split ';') -notcontains $candidate)) {
            $env:PATH = "$candidate;$env:PATH"
        }
    }
}

function Get-UvPath {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    return $null
}

Add-UvPaths
$uvPath = Get-UvPath

if (-not $uvPath) {
    Write-Host "uv not found. Installing uv with the official standalone installer..."
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    Add-UvPaths
    $uvPath = Get-UvPath
}

if (-not $uvPath) {
    throw "uv was installed, but it is not on PATH yet. Open a new terminal, then rerun this script."
}

Push-Location $repoRoot
try {
    $mesaArgs = @("run", "--python", "3.11", "python", "DEPENDENCY/tools/mesa_env.py", "bootstrap")
    if ($InstallMamba) {
        $mesaArgs += "--install-mamba"
    }
    if ($InstallCore) {
        $mesaArgs += "--install-core"
    }
    if ($Yes) {
        $mesaArgs += "--yes"
    }
    if ($ContinueOnError) {
        $mesaArgs += "--continue-on-error"
    }
    if ($WriteHandoff) {
        $mesaArgs += "--write-handoff"
    }
    if ($AnalyzeNondeterministic) {
        $mesaArgs += "--analyze-nondeterministic"
    }
    $mesaArgs += $BootstrapArgs
    & $uvPath @mesaArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
