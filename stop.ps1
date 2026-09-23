$ErrorActionPreference = 'Stop'
$stateFile = Join-Path $PSScriptRoot '.run\processes.json'
if (!(Test-Path -LiteralPath $stateFile)) { Write-Host 'No managed servers to stop.'; return }
$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
foreach ($entry in $state.processes) {
    $process = Get-Process -Id $entry.id -ErrorAction SilentlyContinue
    # Check the start time as well, so a reused PID cannot stop another application.
    if ($process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $entry.started) {
        Stop-Process -Id $process.Id
    }
}
Remove-Item -LiteralPath $stateFile
Write-Host 'HackAlem servers stopped.'
