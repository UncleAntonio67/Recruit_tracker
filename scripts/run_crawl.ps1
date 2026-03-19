param(
  [int]$SinceDays = 180,
  [string]$Proxy = "",
  [ValidateSet("official","core","all")]
  [string]$Mode = "official"
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$py = ".\\.venv\\Scripts\\python.exe"
if (-not (Test-Path $py)) {
  throw "venv not found. Run scripts\\run_local.ps1 once first."
}

if ($Proxy) {
  $env:HTTP_PROXY = $Proxy
  $env:HTTPS_PROXY = $Proxy
}

& $py -m app.crawl run --since-days $SinceDays --mode $Mode
