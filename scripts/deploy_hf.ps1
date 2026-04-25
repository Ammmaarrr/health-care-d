# Push to Hugging Face Spaces (Docker SDK) using a sibling git worktree.
#
# Usage:
#   .\scripts\deploy_hf.ps1 -User <hf-username> -Token <hf-write-token>
#
# Requires: git-lfs installed (https://git-lfs.com).
#
# How it works:
# 1. Adds a sibling git worktree at ..\healthmap-hf-deploy on a new
#    'hf-deploy' branch. Your main working tree is NEVER touched.
# 2. Inside the worktree, copies the built data/ artefacts (parquet,
#    faiss.index) from your main working tree, sets up Git LFS, and
#    commits.
# 3. Force-pushes the worktree branch to the Space's main branch.
# 4. Removes the sibling worktree + branch.

param(
    [Parameter(Mandatory=$true)] [string]$User,
    [Parameter(Mandatory=$true)] [string]$Token,
    [string]$Space = "healthmap-agent"
)

$ErrorActionPreference = "Stop"

$lfsCheck = git lfs version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "git-lfs is not installed. Install from https://git-lfs.com first."
    exit 1
}

# Verify the data we want to deploy actually exists.
$mustExist = @(
    "data\processed\hospitals.parquet",
    "data\index\faiss.index",
    "data\index\faiss_meta.parquet",
    "data\extracted\capabilities.parquet"
)
foreach ($f in $mustExist) {
    if (-not (Test-Path $f)) {
        Write-Error "Missing required deploy artefact: $f. Run 'scripts\01_ingest.py' and 'scripts\02_extract_all.py' first."
        exit 1
    }
}

$repoRoot = (Resolve-Path .).Path
$worktreeDir = Join-Path (Split-Path $repoRoot -Parent) "healthmap-hf-deploy"

Write-Host "Deploying to https://huggingface.co/spaces/$User/$Space" -ForegroundColor Cyan

# Clean up any leftover worktree from a previous run.
if (Test-Path $worktreeDir) {
    Write-Host "Cleaning up previous worktree at $worktreeDir"
    git worktree remove --force $worktreeDir 2>$null | Out-Null
    if (Test-Path $worktreeDir) { Remove-Item -Recurse -Force $worktreeDir }
}
# Also drop a stale local branch if present.
$existing = git branch --list hf-deploy
if ($existing) { git branch -D hf-deploy | Out-Null }

# Create worktree on a fresh branch starting from current HEAD.
git worktree add -B hf-deploy $worktreeDir HEAD | Out-Null

try {
    Push-Location $worktreeDir

    # LFS for binaries.
    git lfs install --local | Out-Null
    git lfs track "*.index"   | Out-Null
    git lfs track "*.parquet" | Out-Null
    git add .gitattributes

    # Copy the built artefacts INTO the worktree, then add them.
    foreach ($f in $mustExist) {
        $src = Join-Path $repoRoot $f
        $dst = Join-Path $worktreeDir $f
        New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
        Copy-Item $src $dst -Force
    }
    git add -f data/processed data/index data/extracted

    # Sanity check: at least one of the parquet/index files must be staged.
    $staged = git diff --cached --name-only
    if (-not ($staged -match "data/.+\.(parquet|index)$")) {
        throw "Nothing staged under data/. Aborting deploy."
    }

    git commit -m "deploy: built FAISS + parquet artefacts via LFS" --allow-empty | Out-Null

    $pushUrl = "https://${User}:${Token}@huggingface.co/spaces/${User}/${Space}"
    git push $pushUrl hf-deploy:main --force
}
finally {
    Pop-Location
    # Clean up worktree + branch.
    git worktree remove --force $worktreeDir 2>$null | Out-Null
    if (Test-Path $worktreeDir) { Remove-Item -Recurse -Force $worktreeDir -ErrorAction SilentlyContinue }
    git branch -D hf-deploy 2>$null | Out-Null
}

Write-Host ""
Write-Host "Done. Space rebuilding at:" -ForegroundColor Green
Write-Host "  https://huggingface.co/spaces/$User/$Space"
Write-Host ""
Write-Host "Secrets (already set if you ran scripts\set_hf_secrets.py):" -ForegroundColor Yellow
Write-Host "  OPENAI_API_KEY"
Write-Host "  TAVILY_API_KEY"
Write-Host "  CORS_ORIGINS"
