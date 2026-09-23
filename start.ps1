param(
    [string]$Python = '',
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$stateDir = Join-Path $root '.run'
$stateFile = Join-Path $stateDir 'processes.json'
$pythonExe = Join-Path $root '.venv\Scripts\python.exe'
$frontend = Join-Path $root 'frontend'

function Get-FreePort([int]$Preferred) {
    foreach ($port in $Preferred..($Preferred + 19)) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
        try { $listener.Start(); return $port }
        catch [System.Net.Sockets.SocketException] { }
        finally { $listener.Stop() }
    }
    throw "No available port near $Preferred."
}

function Wait-Ready([string]$Url, $Process) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($Process.HasExited) { throw "Server exited. Check logs in $stateDir" }
        try {
            $request = [System.Net.WebRequest]::Create($Url)
            $request.Proxy = $null
            $request.Timeout = 2000
            $response = $request.GetResponse()
            $status = [int]$response.StatusCode
            $response.Close()
            if ($status -eq 200) { return }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    throw "Server did not become ready: $Url. Check $stateDir"
}

if (Test-Path -LiteralPath $stateFile) {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $alive = @($state.processes | Where-Object {
        $process = Get-Process -Id $_.id -ErrorAction SilentlyContinue
        $process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $_.started
    })
    if ($alive.Count -eq 2 -and !$Install) {
        Write-Host "Already running: $($state.frontendUrl)"
        Write-Host "API: $($state.backendUrl)/docs"
        return
    }
    & (Join-Path $root 'stop.ps1')
}

if (!(Test-Path -LiteralPath $pythonExe)) {
    if (!$Python) {
        $bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        $candidates = @('py', $bundled, 'python')
        foreach ($candidate in $candidates) {
            $command = Get-Command $candidate -ErrorAction SilentlyContinue
            if (!$command) { continue }
            try { & $command.Source -c 'import os, ensurepip; assert os.name == "nt"' 2>$null }
            catch { continue }
            if ($LASTEXITCODE -eq 0) { $Python = $command.Source; break }
        }
    }
    if (!$Python) { throw 'Install Windows Python 3.12+ or pass -Python C:\path\to\python.exe.' }
    & $Python -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}

$hasDependencies = $false
try {
    & $pythonExe -c 'import fastapi, uvicorn, pandas, numpy' 2>$null
    $hasDependencies = $LASTEXITCODE -eq 0
} catch { }
if (!$hasDependencies -or $Install) {
    & $pythonExe -m pip install -r (Join-Path $root 'backend\requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
}
$node = (Get-Command node -ErrorAction Stop).Source
if (!(Test-Path -LiteralPath (Join-Path $frontend 'node_modules\vite\bin\vite.js')) -or $Install) {
    Push-Location $frontend
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    } finally { Pop-Location }
}

$BackendPort = Get-FreePort $BackendPort
$FrontendPort = Get-FreePort $FrontendPort
$backendUrl = "http://127.0.0.1:$BackendPort"
$frontendUrl = "http://localhost:$FrontendPort"
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$children = @()
$previousTarget = $env:API_TARGET
try {
    $api = Start-Process -FilePath $pythonExe -ArgumentList @(
        '-m', 'uvicorn', 'api:app', '--app-dir', ('"' + (Join-Path $root 'backend') + '"'),
        '--host', '127.0.0.1', '--port', $BackendPort
    ) -WorkingDirectory $root -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput (Join-Path $stateDir 'backend.log') `
      -RedirectStandardError (Join-Path $stateDir 'backend-error.log')
    $children += $api
    Wait-Ready "$backendUrl/health" $api
    Write-Host "API ready: $backendUrl"

    $env:API_TARGET = $backendUrl
    $web = Start-Process -FilePath $node -ArgumentList @(
        ('"' + (Join-Path $frontend 'node_modules\vite\bin\vite.js') + '"'),
        '--host', '127.0.0.1', '--port', $FrontendPort, '--strictPort'
    ) -WorkingDirectory $frontend -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput (Join-Path $stateDir 'frontend.log') `
      -RedirectStandardError (Join-Path $stateDir 'frontend-error.log')
    $children += $web
    Wait-Ready "http://127.0.0.1:$FrontendPort/api/health" $web

    @{
        frontendUrl = $frontendUrl
        backendUrl = $backendUrl
        processes = @($children | ForEach-Object { @{ id = $_.Id; started = $_.StartTime.ToUniversalTime().Ticks.ToString() } })
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $stateFile -Encoding UTF8
    Write-Host "Frontend: $frontendUrl"
    Write-Host "API:      $backendUrl/docs"
    Write-Host 'Stop:     powershell -ExecutionPolicy Bypass -File .\stop.ps1'
} catch {
    foreach ($child in $children) {
        if (!$child.HasExited) { Stop-Process -Id $child.Id -ErrorAction SilentlyContinue }
    }
    throw
} finally {
    $env:API_TARGET = $previousTarget
}
