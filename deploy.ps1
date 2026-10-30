# Deploys Juggle Unicorn to a Pi running Juggle OS: .\deploy.ps1 <name> [-WiFi [-Password <p>]]
# Over SSH (the Pi set up by juggle, with your key), the Pi replaces the app it had with this one and starts it, then
# says whether it's running. Its settings stay (they're in the app's state folder), unless the Pi had a different app.
# -WiFi sends it to the app itself instead (POST /api/update, as a Pico's deploy.ps1 -WiFi does; Juggle OS v0.4 or
# later): no SSH key needed, but it must be this app already running. The Pi tries the new version and goes back to
# the old one if it doesn't keep running. -Password: the app's web password, if it has one.
param(
    [Parameter(Mandatory)]
    [string]$Name,
    [switch]$WiFi,
    [string]$Password
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$app = Join-Path $PSScriptRoot 'app'
$archive = Join-Path ([IO.Path]::GetTempPath()) "juggle-app-$PID.tar"
$target = "juggle@$Name.local"
$url = "http://$Name.local"

try {
    # Windows' own tar; the Pi makes the files root's and readable by the app. App Base's Pico code stays behind
    & "$env:SystemRoot\System32\tar.exe" -c -f $archive -C $app --exclude __pycache__ --exclude state --exclude ./base/pico .
    if ($LASTEXITCODE -ne 0) { throw 'tar failed' }
    $version = (Get-Content (Join-Path $app 'app.json') -Raw | ConvertFrom-Json).version

    if (-not $WiFi) {
        Write-Host "Copying the app to $Name"
        scp -q $archive "${target}:/tmp/app.tar"
        if ($LASTEXITCODE -ne 0) { throw "Couldn't copy the app to $Name" }
        ssh $target 'sudo /usr/lib/juggle/app install /tmp/app.tar; status=$?; rm -f /tmp/app.tar; exit $status'
        if ($LASTEXITCODE -ne 0) { throw "The app didn't install on $Name" }
        Write-Host $url
        return
    }

    $headers = @{}
    if ($Password) {
        $headers.Authorization = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("deploy:$Password"))
    }
    $before = (Invoke-RestMethod "$url/api/update" -Headers $headers -TimeoutSec 15).result
    Write-Host "Sending $version to $Name over the network"
    try {
        Invoke-RestMethod -Method Post "$url/api/update" -Headers $headers -ContentType 'application/x-tar' `
            -InFile $archive -TimeoutSec 60 | Out-Null
    } catch {
        $answer = if ($_.ErrorDetails) { $_.ErrorDetails.Message } else { $null }
        $why = $_.Exception.Message
        if ($answer) { try { $why = ($answer | ConvertFrom-Json).error } catch { $why = $answer } }
        throw "$Name didn't take it: $why"
    }
    # The Pi tries it for 30 s, then says how it went
    Write-Host 'The Pi is trying it (about 40 s)'
    $deadline = (Get-Date).AddSeconds(120)
    do {
        Start-Sleep 5
        try { $result = (Invoke-RestMethod "$url/api/update" -Headers $headers -TimeoutSec 10).result } catch { $result = $null }
        $done = $result -and (-not $before -or $result.time -ne $before.time)
    } until ($done -or (Get-Date) -gt $deadline)
    if (-not $done) { throw "No answer from $Name about the update: see its page, or journalctl -u juggle-app-update" }
    if (-not $result.success) { throw $result.message }
    Write-Host "$($result.message) $url"
}
finally {
    Remove-Item $archive -ErrorAction SilentlyContinue
}
