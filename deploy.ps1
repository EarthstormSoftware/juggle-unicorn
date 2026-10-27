# Deploys ApplPi Unicorn to a Pi running ApplPi OS, over SSH: .\deploy.ps1 [name] (default: jugglepi)
# The Pi replaces the app it had with this one and starts it, then says whether it's running. Its settings stay
# (they're in the app's state folder), unless the Pi had a different app.
param(
    [string]$Name = 'jugglepi'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$app = Join-Path $PSScriptRoot 'app'
$archive = Join-Path ([IO.Path]::GetTempPath()) "applpi-app-$PID.tar"
$target = "applpi@$Name.local"

try {
    # Windows' own tar; the Pi makes the files root's and readable by the app
    tar -c -f $archive -C $app --exclude __pycache__ --exclude state .
    if ($LASTEXITCODE -ne 0) { throw 'tar failed' }
    Write-Host "Copying the app to $Name"
    scp -q $archive "${target}:/tmp/app.tar"
    if ($LASTEXITCODE -ne 0) { throw "Couldn't copy the app to $Name" }
    ssh $target 'sudo /usr/lib/applpi/app install /tmp/app.tar; status=$?; rm -f /tmp/app.tar; exit $status'
    if ($LASTEXITCODE -ne 0) { throw "The app didn't install on $Name" }
    Write-Host "http://$Name.local"
}
finally {
    Remove-Item $archive -ErrorAction SilentlyContinue
}
