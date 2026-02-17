Param(
  [string]$LegacyDir = "legacy"
)
$ErrorActionPreference = "Stop"
if (!(Test-Path $LegacyDir)) { New-Item -ItemType Directory -Force -Path $LegacyDir | Out-Null }

# Move root HTML files to legacy/
Get-ChildItem -Path . -Filter *.html -File | ForEach-Object {
  $dest = Join-Path $LegacyDir $_.Name
  if (Test-Path $dest) { Remove-Item $dest -Force }
  git mv $_.FullName $dest 2>$null
  if ($LASTEXITCODE -ne 0) { Move-Item $_.FullName $dest -Force }
}

Write-Host "Done. Review changes with: git status"
