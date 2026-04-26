param(
    [Parameter(Mandatory = $true)]
    [string]$HostUrl,

    [string]$WorkspacePath = ""
)

$ErrorActionPreference = "Stop"

function Get-DatabricksCli {
    $cmd = Get-Command databricks -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $local = Join-Path $PSScriptRoot "..\.tools\databricks\databricks.exe"
    if (Test-Path $local) {
        return (Resolve-Path $local).Path
    }

    throw "Databricks CLI was not found. Open a fresh terminal or run: winget install Databricks.DatabricksCLI"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$notebooks = Join-Path $repoRoot "databricks\notebooks"
$dbx = Get-DatabricksCli

Write-Host "Authenticating to $HostUrl"
& $dbx auth login --host $HostUrl

if (-not $WorkspacePath) {
    $meJson = & $dbx current-user me --output json
    $me = $meJson | ConvertFrom-Json
    $WorkspacePath = "/Workspace/Users/$($me.userName)/healthmap-agent"
}

$cacheDir = Join-Path $notebooks "__pycache__"
if (Test-Path $cacheDir) {
    Remove-Item -Recurse -Force $cacheDir
}

Write-Host "Importing notebooks to $WorkspacePath"
& $dbx workspace mkdirs $WorkspacePath
& $dbx workspace import-dir $notebooks $WorkspacePath --overwrite

Write-Host "Done. Open Databricks workspace path: $WorkspacePath"
