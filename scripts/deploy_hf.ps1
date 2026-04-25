# Push to Hugging Face Spaces (Docker SDK).
#
# Usage:
#   .\scripts\deploy_hf.ps1 -User <hf-username> -Token <hf-write-token>
#
# Requires: git-lfs installed (https://git-lfs.com).
#
# This creates a temporary 'hf-deploy' branch that:
#  - Sets up Git LFS for *.index and *.parquet (HF rejects raw binaries).
#  - Force-adds the built data/ artefacts that are normally gitignored.
#  - Pushes to the Space's main branch.
# It then returns to your original branch and deletes the deploy branch.

param(
    [Parameter(Mandatory=$true)] [string]$User,
    [Parameter(Mandatory=$true)] [string]$Token,
    [string]$Space = "healthmap-agent"
)

$ErrorActionPreference = "Stop"

# Confirm git-lfs is available.
$lfsCheck = git lfs version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "git-lfs is not installed. Install from https://git-lfs.com first."
    exit 1
}

$origBranch = git rev-parse --abbrev-ref HEAD
Write-Host "Deploying to https://huggingface.co/spaces/$User/$Space" -ForegroundColor Cyan
Write-Host "Original branch: $origBranch"

# Ensure LFS is initialized in this repo.
git lfs install --local | Out-Null

# Build a fresh deploy branch.
git checkout -B hf-deploy

# Track binaries via LFS so the Space repo accepts them.
git lfs track "*.index" | Out-Null
git lfs track "*.parquet" | Out-Null
git add .gitattributes

# Force-add the built artefacts (these are .gitignored on GitHub).
git add -f data/processed data/index data/extracted

git commit -m "deploy: include built data + LFS tracking for *.index, *.parquet" --allow-empty | Out-Null

# One-shot push using credentials embedded in URL (not persisted as a remote).
$pushUrl = "https://${User}:${Token}@huggingface.co/spaces/${User}/${Space}"
git push $pushUrl hf-deploy:main --force

# Cleanup: return to original branch and remove deploy branch.
git checkout $origBranch | Out-Null
git branch -D hf-deploy | Out-Null

Write-Host ""
Write-Host "Done. Space will rebuild at:" -ForegroundColor Green
Write-Host "  https://huggingface.co/spaces/$User/$Space"
Write-Host ""
Write-Host "REMEMBER to set Space secrets in Settings -> Variables and secrets:" -ForegroundColor Yellow
Write-Host "  OPENAI_API_KEY"
Write-Host "  TAVILY_API_KEY"
Write-Host "  CORS_ORIGINS  (e.g. https://your-frontend.vercel.app,http://localhost:3000)"
