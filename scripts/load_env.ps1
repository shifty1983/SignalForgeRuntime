param(
  [string]$Path = ".env"
)

if (-not (Test-Path $Path)) {
  throw "Missing .env file at $Path"
}

Get-Content $Path | ForEach-Object {
  $line = $_.Trim()

  if (-not $line) { return }
  if ($line.StartsWith("#")) { return }
  if ($line -notmatch "=") { return }

  $name, $value = $line.Split("=", 2)
  $name = $name.Trim()
  $value = $value.Trim().Trim('"').Trim("'")

  if ($name) {
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
  }
}

"ENV_LOADED"
"QC_USER_ID loaded: " + [bool]$env:QC_USER_ID
"QC_API_TOKEN loaded: " + [bool]$env:QC_API_TOKEN
