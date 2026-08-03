# Canonical Windows update path for the installed glitch-topstep Hermes profile.
# Stops profile processes, strips VCS artifacts that break Hermes rmtree on update,
# runs `hermes profile update`, then setup.ps1.
[CmdletBinding()]
param(
    [string]$Profile = 'glitch-topstep',
    [switch]$ForceConfig
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$profileRoot = [IO.Path]::GetFullPath(
    (Join-Path $env:LOCALAPPDATA "hermes\profiles\$Profile")
)
if (-not (Test-Path -LiteralPath $profileRoot -PathType Container)) {
    throw "Profile not found: $profileRoot"
}

function Stop-ProfileProcesses {
    Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match [regex]::Escape($Profile) } |
        ForEach-Object {
            Write-Host "Stopping PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Seconds 2
}

function Remove-StagingArtifacts {
    param([string]$Root)
    foreach ($name in @('.git', '.gitattributes')) {
        $path = Join-Path $Root $name
        if (-not (Test-Path -LiteralPath $path)) { continue }
        if (Test-Path -LiteralPath $path -PathType Container) {
            cmd /c "attrib -R `"$path\*`" /S /D" 2>$null | Out-Null
        }
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $path) {
            throw "Could not remove staging artifact: $path"
        }
        Write-Host "Removed $name"
    }
    $lock = Join-Path $Root 'state\direct-cycle.lock'
    if (Test-Path -LiteralPath $lock -PathType Leaf) {
        Remove-Item -LiteralPath $lock -Force
        Write-Host 'Removed state\direct-cycle.lock'
    }
}

function Get-RecordedSource {
    $yaml = Join-Path $profileRoot 'distribution.yaml'
    foreach ($line in Get-Content -LiteralPath $yaml) {
        if ($line -match '^source:\s*(.+)$') {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    throw 'distribution.yaml has no source: field — reinstall from GitHub first.'
}

$source = Get-RecordedSource
if ($source -match '^[A-Za-z]:\\' -or $source -match '^/') {
    Write-Warning @"
Recorded source is a local path ($source).
Hermes copies .git from local paths and Windows updates fail.
Reinstall once from GitHub, then use this script again:
  hermes profile install github.com/GlitchTrader/glitch-topstep-hermes-profile --name glitch-topstep --force -y
"@
    throw 'Refusing to update from a local-path distribution source.'
}

Write-Host "Updating profile '$Profile' from $source"
Stop-ProfileProcesses
Remove-StagingArtifacts -Root $profileRoot

$updateArgs = @('profile', 'update', $Profile, '-y')
if ($ForceConfig) { $updateArgs += '--force-config' }
& hermes @updateArgs
if ($LASTEXITCODE -ne 0) {
    throw "hermes profile update failed with exit code $LASTEXITCODE"
}

Remove-StagingArtifacts -Root $profileRoot

$setup = Join-Path $profileRoot 'setup.ps1'
& powershell -ExecutionPolicy Bypass -File $setup
if ($LASTEXITCODE -ne 0) {
    throw "setup.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host "Profile '$Profile' updated successfully."
