# Reset the live monitor. The running server defaults to port 8001.
param([string]$BaseUrl = 'http://127.0.0.1:8001')

$ErrorActionPreference = 'Stop'
Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/api/live-sync" -Method Post -ContentType 'application/json' -Body '{"event_type":"reset"}' | Out-Null
Write-Host 'Monitor reset successfully.'
