$ErrorActionPreference = "Stop"
$vars = @(
  "VITE_ETH_RPC","VITE_POLYGON_RPC","VITE_BNB_RPC",
  "VITE_COSMOS_RPC","VITE_COSMOS_DENOM",
  "VITE_BTC_API","VITE_DAG_NODE"
)
$missing = @()
foreach ($v in $vars) {
  if ([string]::IsNullOrWhiteSpace([System.Environment]::GetEnvironmentVariable($v))) { $missing += $v }
}
if ($missing.Count -gt 0) {
  Write-Error "Faltan variables de entorno: $($missing -join ', ')"
  exit 1
} else {
  Write-Host "Preflight OK"
}
