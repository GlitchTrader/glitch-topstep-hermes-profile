# One-shot: unblock Hermes profile install/update on Windows (ReadOnly skills/plugins).
# Preserves .env, config.yaml, and state/.
[CmdletBinding()]
param(
    [string]$Profile = 'glitch-topstep',
    [switch]$InstallOnly,
    [switch]$UpdateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$profileRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "hermes\profiles\$Profile"))
$source = 'github.com/GlitchTrader/glitch-topstep-hermes-profile'
$envBackup = Join-Path $env:TEMP "glitch-topstep-env-backup-$Profile.env"
$stateBackup = Join-Path $env:TEMP "glitch-topstep-state-backup-$Profile"

if (-not (Test-Path -LiteralPath $profileRoot -PathType Container)) {
    Write-Host "Profile not found at $profileRoot - will install fresh."
}

function Stop-HermesProfile {
    $env:HERMES_HOME = $profileRoot
    try { & hermes --profile $Profile gateway stop 2>$null | Out-Null } catch { }
    Get-Process -Name 'hermes*' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path -match 'hermes' } |
        ForEach-Object {
            Write-Host "Stopping Hermes PID $($_.Id)"
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
    $escaped = [regex]::Escape($profileRoot)
    foreach ($name in @('python.exe', 'python3.exe', 'python3.12.exe', 'python3.11.exe')) {
        Get-CimInstance Win32_Process -Filter "name='$name'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match $escaped -or $_.CommandLine -match [regex]::Escape($Profile) } |
            ForEach-Object {
                Write-Host "Stopping PID $($_.ProcessId) ($name)"
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
    }
    Start-Sleep -Seconds 3
}

function Remove-StaleDistributionTrees {
    param([string]$Root)
    foreach ($rel in @('skills', 'plugins')) {
        $path = Join-Path $Root $rel
        if (-not (Test-Path -LiteralPath $path)) { continue }
        Clear-ReadOnlyTree -Path $path
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $path) {
            throw "Could not remove stale distribution tree: $rel"
        }
        Write-Host "Removed stale tree: $rel"
    }
}

function Clear-ReadOnlyTree {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    cmd /c "attrib -R `"$Path`" /S /D" 2>$null | Out-Null
    if (Test-Path -LiteralPath $Path -PathType Container) {
        cmd /c "attrib -R `"$Path\*`" /S /D" 2>$null | Out-Null
    }
}

function Backup-OperatorState {
    if (Test-Path -LiteralPath (Join-Path $profileRoot '.env')) {
        Copy-Item -LiteralPath (Join-Path $profileRoot '.env') -Destination $envBackup -Force
        Write-Host "Backed up .env -> $envBackup"
    }
    $stateDir = Join-Path $profileRoot 'state'
    if (Test-Path -LiteralPath $stateDir -PathType Container) {
        if (Test-Path -LiteralPath $stateBackup) {
            Remove-Item -LiteralPath $stateBackup -Recurse -Force
        }
        Copy-Item -LiteralPath $stateDir -Destination $stateBackup -Recurse -Force
        Write-Host "Backed up state/ -> $stateBackup"
    }
}

function Restore-OperatorState {
    if (Test-Path -LiteralPath $envBackup) {
        Copy-Item -LiteralPath $envBackup -Destination (Join-Path $profileRoot '.env') -Force
        Write-Host "Restored .env"
    }
    $stateDir = Join-Path $profileRoot 'state'
    if (Test-Path -LiteralPath $stateBackup -PathType Container) {
        if (-not (Test-Path -LiteralPath $stateDir)) {
            New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
        }
        Copy-Item -LiteralPath (Join-Path $stateBackup '*') -Destination $stateDir -Recurse -Force
        Write-Host "Restored state/"
    }
}

function Ensure-SourceField {
    $yaml = Join-Path $profileRoot 'distribution.yaml'
    if (-not (Test-Path -LiteralPath $yaml)) { return }
    $content = Get-Content -LiteralPath $yaml -Raw
    if ($content -match '(?m)^source:\s*\S') { return }
    $lines = Get-Content -LiteralPath $yaml
    $out = @()
    $inserted = $false
    foreach ($line in $lines) {
        $out += $line
        if (-not $inserted -and $line -match '^author:\s*') {
            $out += "source: $source"
            $inserted = $true
        }
    }
    if (-not $inserted) { $out = @("source: $source") + $lines }
    Set-Content -LiteralPath $yaml -Value $out -Encoding UTF8
    Write-Host "Added source: to distribution.yaml"
}

Set-Location $env:TEMP
Stop-HermesProfile
Backup-OperatorState

if (Test-Path -LiteralPath $profileRoot) {
    foreach ($rel in @('skills', 'plugins', 'scripts', 'tests', 'docs')) {
        Clear-ReadOnlyTree -Path (Join-Path $profileRoot $rel)
    }
    Remove-StaleDistributionTrees -Root $profileRoot
    Ensure-SourceField
}

if (-not $UpdateOnly) {
    Write-Host "Running: hermes profile install $source --name $Profile --force -y"
    & hermes profile install $source --name $Profile --force -y
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'Install failed; removing skills/plugins/.github and retrying once.'
        Remove-StaleDistributionTrees -Root $profileRoot
        & hermes profile install $source --name $Profile --force -y
        if ($LASTEXITCODE -ne 0) { throw "hermes profile install failed with exit code $LASTEXITCODE" }
    }
}

$repoRoot = $env:GLITCH_TOPSTEP_PROFILE_REPO
if (-not $repoRoot) {
    $candidate = 'C:\Users\arifr\OneDrive\Documentos\GitHub\glitch-topstep-hermes-profile'
    if (Test-Path -LiteralPath $candidate) { $repoRoot = $candidate }
}
if ($repoRoot -and (Test-Path -LiteralPath $repoRoot)) {
    foreach ($rel in @('setup.ps1', 'scripts\safe-profile-update.ps1', 'scripts\unblock-profile-install.ps1')) {
        $src = Join-Path $repoRoot $rel
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $profileRoot $rel) -Force
            Write-Host "Synced patched $rel from repo"
        }
    }
    $githubSrc = Join-Path $repoRoot '.github'
    if (-not (Test-Path -LiteralPath (Join-Path $profileRoot '.github')) -and (Test-Path -LiteralPath $githubSrc)) {
        Copy-Item -LiteralPath $githubSrc -Destination (Join-Path $profileRoot '.github') -Recurse -Force
        Write-Host 'Synced .github from local repo (until GitHub distribution_owned includes it)'
    }
}

$setup = Join-Path $profileRoot 'setup.ps1'
if (Test-Path -LiteralPath $setup) {
    Write-Host 'Running setup.ps1 (-SkipIntegrityCheck; patched scripts differ from published SHA256SUMS)'
    & powershell -ExecutionPolicy Bypass -File $setup -SkipIntegrityCheck -SkipGatewayInstall
    if ($LASTEXITCODE -ne 0) { throw "setup.ps1 failed with exit code $LASTEXITCODE" }
}

$env:HERMES_HOME = $profileRoot
try { & hermes --profile $Profile gateway install --start-now 2>&1 | Out-String | Write-Host } catch { }
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'Gateway scheduled-task install failed; starting gateway directly.'
    Start-Process -FilePath (Get-Command hermes).Source -ArgumentList @('--profile', $Profile, 'gateway') -WindowStyle Hidden -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
}

if (-not $InstallOnly) {
    $safeUpdate = Join-Path $profileRoot 'scripts\safe-profile-update.ps1'
    if ((Test-Path -LiteralPath $safeUpdate) -and -not $InstallOnly) {
        Write-Host 'Skipping safe-profile-update (install+setup already ran).'
    }
}

$scriptsDir = Join-Path $profileRoot 'scripts'
$cronList = & hermes --profile $Profile cron list 2>&1 | Out-String
if ($cronList -match 'No scheduled jobs') {
    Write-Host 'Creating Topstep cron jobs...'
    & hermes --profile $Profile cron create '* * * * *' --name glitch-topstep-direct-operator --script launch-topstep-cycle.py --no-agent --deliver local --workdir $scriptsDir | Out-Null
    & hermes --profile $Profile cron create '*/30 * * * *' --name glitch-topstep-learning-supervisor --script launch-topstep-learning.py --no-agent --deliver local --workdir $scriptsDir | Out-Null
    & hermes --profile $Profile cron create '* * * * *' --name glitch-topstep-wake-monitor --script launch-wake-trigger-monitor.py --no-agent --deliver local --workdir $scriptsDir | Out-Null
}

Restore-OperatorState

Write-Host "Done. Verify:"
Write-Host "  hermes cron list"
Write-Host "  hermes gateway status"
Write-Host "  hermes cron resume <job-id>   # jobs start paused on fresh setup"
