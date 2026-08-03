[CmdletBinding()]
param(
    [string]$Profile = 'glitch-topstep'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Profile -ne 'glitch-topstep') {
    throw 'This distribution must be installed as the glitch-topstep Hermes profile.'
}

$profileRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$expectedRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'hermes\profiles\glitch-topstep'))
if ($profileRoot.TrimEnd('\') -ne $expectedRoot.TrimEnd('\')) {
    throw "Run setup from the installed glitch-topstep profile: $expectedRoot"
}

function Assert-DistributionIntegrity {
    $manifestPath = Join-Path $profileRoot 'SHA256SUMS'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'SHA256SUMS is missing; reinstall the profile before setup.'
    }
    foreach ($line in Get-Content -LiteralPath $manifestPath) {
        $line = $line.TrimStart([char]0xFEFF)
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split '\s{2,}', 2
        if ($parts.Count -ne 2 -or $parts[0] -notmatch '^[0-9A-Fa-f]{64}$') {
            throw "Invalid SHA256SUMS line: $line"
        }
        $relative = $parts[1].Replace('/', '\')
        $path = [IO.Path]::GetFullPath((Join-Path $profileRoot $relative))
        if (-not $path.StartsWith($profileRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Manifest path escapes the profile: $relative"
        }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Distributed file is missing: $relative"
        }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        if ($actual -ne $parts[0].ToUpperInvariant()) {
            throw "Distributed file checksum mismatch: $relative"
        }
    }
}

function Get-HermesJobs {
    $jobsPath = Join-Path $profileRoot 'cron\jobs.json'
    if (-not (Test-Path -LiteralPath $jobsPath -PathType Leaf)) { return @() }
    $document = Get-Content -LiteralPath $jobsPath -Raw | ConvertFrom-Json
    return @($document.jobs)
}

function Get-ScheduleText($job) {
    if ($null -eq $job) { return '' }
    if ($job.schedule.display) { return [string]$job.schedule.display }
    return [string]$job.schedule.expr
}

function Ensure-CronJob {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Schedule,
        [Parameter(Mandatory = $true)][string]$Script,
        [Parameter(Mandatory = $true)][string]$Workdir
    )
    $matches = @(Get-HermesJobs | Where-Object name -eq $Name)
    if ($matches.Count -gt 1) {
        throw "Multiple $Name jobs exist; refusing to guess which one is authoritative."
    }
    $preserveEnabled = $matches.Count -eq 1 -and [bool]$matches[0].enabled
    if ($matches.Count -eq 1) {
        $jobId = [string]$matches[0].id
        & hermes cron edit $jobId --schedule $Schedule --script $Script --no-agent --workdir $Workdir | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not reconcile $Name." }
    }
    else {
        & hermes cron create $Schedule --name $Name --script $Script --no-agent --deliver local --workdir $Workdir | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not create $Name." }
        $created = @(Get-HermesJobs | Where-Object name -eq $Name)
        if ($created.Count -ne 1) { throw "$Name was not created exactly once." }
        $jobId = [string]$created[0].id
        $preserveEnabled = $false
    }
    $current = @(Get-HermesJobs | Where-Object name -eq $Name)
    if ($current.Count -ne 1) { throw "$Name reconciliation did not leave exactly one job." }
    if ($preserveEnabled -and -not [bool]$current[0].enabled) {
        & hermes cron resume $jobId | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not preserve enabled state for $Name." }
    }
    elseif (-not $preserveEnabled -and [bool]$current[0].enabled) {
        & hermes cron pause $jobId | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not leave $Name paused." }
    }
    $verified = @(Get-HermesJobs | Where-Object name -eq $Name)[0]
    if ((Get-ScheduleText $verified) -ne $Schedule `
        -or -not [bool]$verified.no_agent `
        -or [string]$verified.script -ne $Script `
        -or [IO.Path]::GetFullPath([string]$verified.workdir) -ne [IO.Path]::GetFullPath($Workdir) `
        -or [bool]$verified.enabled -ne $preserveEnabled) {
        throw "$Name persisted with the wrong schedule, script, workdir, or enabled state."
    }
    return [ordered]@{ name = $Name; id = $jobId; enabled = $preserveEnabled; schedule = $Schedule }
}

Assert-DistributionIntegrity
$requiredFiles = @(
    'scripts\common.py',
    'scripts\launch-topstep-cycle.py',
    'scripts\run-topstep-cycle.py',
    'scripts\launch-topstep-learning.py',
    'scripts\run-topstep-learning.py',
    'plugins\topstep-control\plugin.yaml',
    'plugins\topstep-control\__init__.py'
)
foreach ($relative in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $profileRoot $relative) -PathType Leaf)) {
        throw "Required distribution file is missing: $relative"
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $profileRoot '.env') -PathType Leaf)) {
    Copy-Item -LiteralPath (Join-Path $profileRoot '.env.EXAMPLE') -Destination (Join-Path $profileRoot '.env')
}
New-Item -ItemType Directory -Force -Path (Join-Path $profileRoot 'state') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $profileRoot 'state\supervisor') | Out-Null

& hermes -p $Profile plugins enable topstep-control --no-allow-tool-override | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not enable the Topstep control plugin.' }
& hermes -p $Profile gateway install --start-now --start-on-login
if ($LASTEXITCODE -ne 0) { throw 'Could not install the supervised Glitch Topstep Hermes gateway.' }

$hermesCommand = Get-Command hermes -ErrorAction Stop
$python = Join-Path (Split-Path $hermesCommand.Source -Parent) 'python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Could not locate the Hermes Python runtime: $python"
}

$previousHermesHome = $env:HERMES_HOME
try {
    $env:HERMES_HOME = $profileRoot
    & $python -c "from hermes_cli.config import load_config, save_config; from hermes_cli.fallback_cmd import _write_chain; c=load_config(); m=c.setdefault('model', {}); m['default']='gpt-5.6-luna'; m['provider']='openai-codex'; m['base_url']='https://chatgpt.com/backend-api/codex'; m['api_mode']='chat_completions'; a=c.setdefault('agent', {}); a['reasoning_effort']='medium'; a.pop('reasoning_overrides', None); _write_chain(c, []); save_config(c)"
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not reconcile the Topstep profile to Luna-medium without model fallbacks.'
    }
}
finally {
    $env:HERMES_HOME = $previousHermesHome
}

$previousHermesHome = $env:HERMES_HOME
try {
    $env:HERMES_HOME = $profileRoot
    # Every minute: capture frames, deliver pending intents, and invoke LLM on the
    # flat 5-minute boundary (or every minute while positioned).
    $directJob = Ensure-CronJob `
        -Name 'glitch-topstep-direct-operator' `
        -Schedule '* * * * *' `
        -Script 'launch-topstep-cycle.py' `
        -Workdir (Join-Path $profileRoot 'scripts')
    $learningJob = Ensure-CronJob `
        -Name 'glitch-topstep-learning-supervisor' `
        -Schedule '*/30 * * * *' `
        -Script 'launch-topstep-learning.py' `
        -Workdir (Join-Path $profileRoot 'scripts')
}
finally {
    $env:HERMES_HOME = $previousHermesHome
}

$gatewayCompatibility = 'not_checked'
$previousHermesHome = $env:HERMES_HOME
try {
    $env:HERMES_HOME = $profileRoot
    $check = @'
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import configure_environment, request_json
from compatibility import compatibility_summary, verify_gateway_compatibility
configure_environment()
status, health = request_json('/health')
if status != 200:
    print(json.dumps({'state': 'unavailable', 'http_status': status}))
else:
    try:
        verify_gateway_compatibility(health)
        print(json.dumps({'state': 'compatible', 'summary': compatibility_summary(health)}))
    except RuntimeError as error:
        print(json.dumps({'state': 'incompatible', 'summary': compatibility_summary(health), 'error': str(error)}))
'@
    $checkPath = Join-Path $profileRoot 'scripts\_setup_gateway_check.py'
    Set-Content -LiteralPath $checkPath -Value $check -Encoding UTF8
    $checkOutput = & $python $checkPath 2>$null
    Remove-Item -LiteralPath $checkPath -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -eq 0 -and $checkOutput) {
        $gatewayCompatibility = ($checkOutput | ConvertFrom-Json)
    }
    else {
        $gatewayCompatibility = @{ state = 'unavailable' }
    }
}
catch {
    $gatewayCompatibility = @{ state = 'unavailable'; error = $_.Exception.Message }
}
finally {
    $env:HERMES_HOME = $previousHermesHome
}

[ordered]@{
    schema_version = 'glitch.topstep.hermes.setup.v1'
    profile = $Profile
    distribution_version = '0.1.5'
    gateway_supervised = $true
    gateway_compatibility = $gatewayCompatibility
    plugin_enabled = $true
    jobs = @($directJob, $learningJob)
    fresh_install_jobs_paused = (-not $directJob.enabled -and -not $learningJob.enabled)
    next = 'Set GLITCH_TOPSTEP_LOCAL_TOKEN in .env, start the local glitch-topstep gateway, then use /topstep_status and /trade.'
} | ConvertTo-Json -Depth 5
