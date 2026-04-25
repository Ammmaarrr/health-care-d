# Push to Hugging Face Spaces (Docker SDK).
#
# Usage:
#   1. Create a Space at https://huggingface.co/new-space
#      (SDK = Docker, hardware = CPU basic free).
#   2. Generate a token at https://huggingface.co/settings/tokens (write scope).
#   3. Run this from the project root:
#        .\scripts\deploy_hf.ps1 -User <hf-username>
#      Enter the token as the password when prompted.
#
# This creates a temporary 'hf-deploy' branch that *includes* the built
# data/ artefacts, force-pushes it to the Space's main branch, then
# returns to your original branch.

param(
    [Parameter(Mandatory=$true)]
    [string]$User,
    [string]$Space = "healthmap-agent"
)

$ErrorActionPreference = "Stop"

Write-Host "Deploying to https://huggingface.co/spaces/$User/$Space" -ForegroundColor Cyan

# Stash current branch.
$origBranch = git rev-parse --abbrev-ref HEAD

# Add HF as a remote if not already.
$existing = git remote | Where-Object { $_ -eq "hf" }
if (-not $existing) {
    git remote add hf "https://huggingface.co/spaces/$User/$Space"
}

# Build a fresh deploy branch that includes data/.
git checkout -B hf-deploy
git add -f data/processed data/index data/extracted
git commit -m "deploy: include built data" --allow-empty

# Force push to the Space's main branch.
git push hf hf-deploy:main --force

# Cleanup.
git checkout $origBranch
git branch -D hf-deploy

Write-Host ""
Write-Host "Done. Space will rebuild at:" -ForegroundColor Green
Write-Host "  https://huggingface.co/spaces/$User/$Space"
Write-Host ""
Write-Host "Don't forget to set Space secrets in Settings -> Variables and secrets:" -ForegroundColor Yellow
Write-Host "  OPENAI_API_KEY"
Write-Host "  TAVILY_API_KEY"
Write-Host "  CORS_ORIGINS  (e.g. https://your-frontend.vercel.app)"
