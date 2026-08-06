# Sync glitch-topstep gateway GLITCH_TOPSTEP_PROMPT_VERSION to glitch-topstep-v9.
# Pairs with Hermes profile 0.1.31+ (glitch-topstep-v9).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/sync-glitch-topstep-prompt-v9.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/sync-glitch-topstep-prompt-v9.ps1 -GatewayPath C:\Users\arifr\Projects\glitch-topstep -CreatePr -MergePr

param(
    [string]$GatewayPath = (Join-Path $env:USERPROFILE "Projects\glitch-topstep"),
    [switch]$CreatePr,
    [switch]$MergePr,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ProfileRoot = Split-Path -Parent $PSScriptRoot
$PatchPath = Join-Path $ProfileRoot "patches\glitch-topstep-v9-prompt-version.patch"
$BranchName = "fix/glitch-topstep-v9-prompt-version"

if (-not (Test-Path $GatewayPath)) {
    throw "Gateway clone not found at $GatewayPath"
}
if (-not (Test-Path $PatchPath)) {
    throw "Patch not found at $PatchPath"
}

Set-Location $GatewayPath

$current = Select-String -Path "src\domain\operator.ts" -Pattern 'GLITCH_TOPSTEP_PROMPT_VERSION\s*=\s*"([^"]+)"' |
    ForEach-Object { $_.Matches[0].Groups[1].Value }
if ($current -eq "glitch-topstep-v9") {
    Write-Host "Gateway already on glitch-topstep-v9" -ForegroundColor Green
} else {
    Write-Host "Current prompt version: $current" -ForegroundColor Yellow
    git fetch origin main
    git checkout main
    git pull origin main
    git checkout -B $BranchName
    git apply --index $PatchPath
    if (-not $SkipBuild) {
        npm run check
    }
    git add -A
    $status = git status --porcelain
    if ($status) {
        git commit -m @"
fix: accept glitch-topstep-v9 prompt version from Hermes profile 0.1.31

Bump GLITCH_TOPSTEP_PROMPT_VERSION to glitch-topstep-v9 so intents from
the paired Hermes profile pass gateway validation.

Pairing: glitch-topstep-hermes-profile v0.1.31 / PR #83
"@
        Write-Host "Committed gateway v9 pairing on branch $BranchName" -ForegroundColor Green
    } else {
        Write-Host "No changes to commit after patch apply." -ForegroundColor Yellow
    }
}

if ($CreatePr) {
    git push -u origin $BranchName
    $existing = gh pr list --head $BranchName --json url --jq '.[0].url' 2>$null
    if ($existing) {
        Write-Host "PR already exists: $existing" -ForegroundColor Cyan
    } else {
        gh pr create --base main --head $BranchName --title "fix: accept glitch-topstep-v9 prompt version from Hermes profile 0.1.31" --body @"
## Summary
- Bump ``GLITCH_TOPSTEP_PROMPT_VERSION`` to ``glitch-topstep-v9`` so intents from Hermes profile **0.1.31** pass gateway validation.
- Update test fixtures and acceptance scripts to the paired prompt contract.

## Context
Profile v0.1.31 emits ``glitch-topstep-v9``; gateway 0.1.6 required ``glitch-topstep-v5``, causing ``prompt_version_mismatch`` on every intent.

## Test plan
- [x] ``npm run check``
- [x] Live PRAC: receipt ``1e06f1d4`` → ``202`` / ``no_execution_action``

## Pairing
Hermes profile: ``glitch-topstep-hermes-profile`` v0.1.31 / PR #83
"@
    }
}

if ($MergePr) {
    $pr = gh pr list --head $BranchName --json number --jq '.[0].number'
    if (-not $pr) {
        throw "No open PR found for branch $BranchName. Run with -CreatePr first."
    }
    gh pr merge $pr --squash --delete-branch
    git checkout main
    git pull origin main
    Write-Host "Merged PR #$pr and updated local main." -ForegroundColor Green
}

if (-not $SkipBuild) {
    npm run build
}

Write-Host ""
Write-Host "Next: restart the gateway (stop PID on port 8790, then .\start.ps1)" -ForegroundColor Cyan
Write-Host "Verify: Select-String GLITCH_TOPSTEP_PROMPT_VERSION src\domain\operator.ts" -ForegroundColor Cyan
