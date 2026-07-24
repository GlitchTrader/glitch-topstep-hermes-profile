[CmdletBinding()]
param(
    [string]$Profile = 'glitch-topstep',
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Profile -ne 'glitch-topstep') {
    throw 'Only the installed glitch-topstep Hermes profile may be reset by this script.'
}

$profileRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'hermes\profiles\glitch-topstep'))
$jobsPath = Join-Path $profileRoot 'cron\jobs.json'
$setupPath = Join-Path $profileRoot 'setup.ps1'

if (-not (Test-Path -LiteralPath $profileRoot -PathType Container)) {
    throw "Profile root is missing: $profileRoot"
}
if (-not (Test-Path -LiteralPath $setupPath -PathType Leaf)) {
    throw "Profile setup script is missing: $setupPath"
}

function Assert-ChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $fullPath = [IO.Path]::GetFullPath($Path)
    $fullRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if (-not $fullPath.StartsWith($fullRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing reset target outside the expected root: $fullPath"
    }
    return $fullPath
}

function Remove-ResetTarget {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $target = Assert-ChildPath -Path $Path -Root $Root
    if (-not (Test-Path -LiteralPath $target)) { return $false }
    Remove-Item -LiteralPath $target -Recurse -Force
    if (Test-Path -LiteralPath $target) {
        throw "Reset target could not be removed: $target"
    }
    return $true
}

function Get-HermesJobs {
    if (-not (Test-Path -LiteralPath $jobsPath -PathType Leaf)) { return @() }
    return @((Get-Content -LiteralPath $jobsPath -Raw | ConvertFrom-Json).jobs)
}

$enabledJobs = @(Get-HermesJobs | Where-Object { [bool]$_.enabled -or [string]$_.state -eq 'active' })
if ($enabledJobs.Count -gt 0) {
    throw ('Every Hermes job must be paused before reset: ' + (($enabledJobs | ForEach-Object name) -join ', '))
}

$profileTargets = @(
    'cache',
    'cron',
    'logs',
    'memories',
    'plans',
    'sandboxes',
    'sessions',
    'state',
    'workspace',
    'state.db',
    'state.db-shm',
    'state.db-wal',
    'verification_evidence.db',
    '.hermes_history',
    'gateway-starts.log'
)

$preview = [ordered]@{
    schema_version = 'glitch.topstep.trading_epoch_reset.v1'
    mode = if ($Apply) { 'apply' } else { 'preview' }
    profile = $Profile
    all_jobs_paused = $true
    profile_targets = $profileTargets.Count
    preserved = @(
        'Hermes authentication and profile configuration',
        'distributed SOUL, skills, plugin, scripts, and setup',
        'local glitch-topstep Node gateway repository and ProjectX credentials'
    )
    destroyed = @(
        'all Hermes sessions and native memories',
        'all Hermes cron jobs and cron execution history',
        'all profile-local decision, receipt, outcome, learning, and supervisor state'
    )
}

if (-not $Apply) {
    $preview | ConvertTo-Json -Depth 5
    return
}

& hermes -p $Profile gateway stop | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Could not stop the Glitch Topstep Hermes gateway before reset.'
}

$removed = [Collections.Generic.List[string]]::new()
foreach ($relative in $profileTargets) {
    $target = Join-Path $profileRoot $relative
    if (Remove-ResetTarget -Path $target -Root $profileRoot) {
        $removed.Add($target)
    }
}

$epochPath = Join-Path $profileRoot 'state\epoch.json'
New-Item -ItemType Directory -Force -Path (Split-Path $epochPath -Parent) | Out-Null
[ordered]@{
    schema_version = 'glitch.topstep.epoch.v1'
    epoch_id = [guid]::NewGuid().ToString()
    reset_utc = [datetime]::UtcNow.ToString('o')
    profile_distribution = '0.1.0'
    prior_state_preserved = $false
    reset_scope = 'hermes_profile_only'
} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $epochPath -Encoding utf8

& powershell -NoProfile -ExecutionPolicy Bypass -File $setupPath -Profile $Profile | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Clean profile setup failed after reset.'
}

[ordered]@{
    schema_version = 'glitch.topstep.trading_epoch_reset.v1'
    mode = 'applied'
    reset_utc = [datetime]::UtcNow.ToString('o')
    profile = $Profile
    removed_targets = $removed.Count
    jobs_paused = $true
    next = 'Restart the Node gateway if needed, then use /topstep_status and /trade.'
} | ConvertTo-Json -Depth 5
