# Local author regression check only: renders text in a fresh temporary directory.
# Never invokes rendered scripts, contacts hosts, or starts services.
$ErrorActionPreference = 'Stop'
$deploy = Split-Path $PSScriptRoot -Parent
$renderer = Join-Path $deploy 'Render-Plan.ps1'
$templates = @(Get-ChildItem -LiteralPath $deploy -File | Where-Object Name -Match '\.in($|\.sh$)' | Sort-Object Name)
$manifest = ($templates | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower() + '  ' + $_.Name }) -join "`n"
$m7TestState = @{ ExpectedHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($manifest))).ToLower()
}
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('dr-m7-render-' + [guid]::NewGuid().ToString('N'))
$m7TestState.Destination = Join-Path $scratch 'dry-run'
$m7TestState.OverrideValue = $null
$m7TestState.Values = @{
    APP_USER='fixture'; APP_GROUP='fixture'; APP_DIRECTORY='/opt/fixture'; CONTROL_ENV_FILE='/etc/fixture.env';
    APP_PYTHON_ABSOLUTE_PATH='/opt/fixture/bin/python'; M5_API_ENTRYPOINT='fixture:app'; APP_PORT='8765';
    RUNS_DIRECTORY='/var/lib/fixture/runs'; OPERATOR_IPV4_CIDR='192.0.2.1/32'; SANDBOX_IPV4='192.0.2.2';
    CONTROL_IPV4='192.0.2.3'; DNS_IPV4='192.0.2.4'; NTP_IPV4='192.0.2.5'; DOCKER_ABSOLUTE_PATH='/usr/bin/docker';
    G3_SUBDOMAIN='fixture.invalid'; G4_DOCKER_VERSION='fixture'; PINNED_DOCKER_CLI_VERSION='fixture';
    PINNED_CONTAINERD_VERSION='fixture'; PINNED_BUILDX_VERSION='fixture'; PINNED_COMPOSE_VERSION='fixture';
    G8_PLAN_REGION_OS='fixture'
}
function Read-Host {
    param([string]$Prompt)
    switch -Exact ($Prompt) {
        'Absolute template directory' { return $deploy }
        'Expected SHA-256 of the sorted template hash manifest' { return $m7TestState.ExpectedHash }
        'Absolute NEW destination directory (dry-run does not create it)' { return $m7TestState.Destination }
        'Press Enter to close' { return '' }
        default {
            if ($Prompt -notmatch '^Reviewed non-secret value for ([A-Z0-9_]+)$') { throw "Unexpected prompt: $Prompt" }
            $name = $Matches[1]
            if ($null -ne $m7TestState.OverrideValue) { return $m7TestState.OverrideValue }
            if (-not $m7TestState.Values.ContainsKey($name)) { throw "Missing fixture value: $name" }
            return $m7TestState.Values[$name]
        }
    }
}
function Assert-Check([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

$preview = @(& $renderer)
Assert-Check (-not (Test-Path -LiteralPath $scratch)) 'Dry-run created output'
Assert-Check (($preview | Where-Object { $_ -like 'PREVIEW *' }).Count -eq 6) 'Expected all six template previews'
Assert-Check (($preview -join "`n") -notmatch '<<[A-Z0-9_]+>>') 'Unresolved placeholder survived rendering'
Assert-Check (($preview -join "`n").Contains("'<<'")) 'Literal shell guard was lost'

$m7TestState.Destination = Join-Path $scratch 'written'
$null = & $renderer -WriteFiles
$written = @(Get-ChildItem -LiteralPath $m7TestState.Destination -File)
Assert-Check ($written.Count -eq 6) 'Expected exactly six rendered files'
foreach ($file in $written) {
    Assert-Check ([IO.File]::ReadAllText($file.FullName) -notmatch '<<[A-Z0-9_]+>>') "Placeholder in $($file.Name)"
}
foreach ($name in @('docker-channel.sh', 'docker-install.sh')) {
    Assert-Check ([IO.File]::ReadAllText((Join-Path $m7TestState.Destination $name)).Contains("'<<'")) "Guard missing from $name"
}

foreach ($bad in @('<<UNRESOLVED_NAME>>', 'UNSET', '')) {
    $m7TestState.Destination = Join-Path $scratch ('refused-' + [guid]::NewGuid().ToString('N'))
    $m7TestState.OverrideValue = $bad
    $refused = $false
    try { $null = & $renderer -WriteFiles }
    catch {
        if ($_.Exception.Message -ne 'Unresolved or multiline value refused') { throw }
        $refused = $true
    }
    Assert-Check $refused 'Unresolved substitution was accepted'
    Assert-Check (-not (Test-Path -LiteralPath $m7TestState.Destination)) 'Refused render wrote output'
}
[pscustomobject]@{ Result='PASS'; Templates=6; Refusals=3; Scratch=$scratch; Scope='author-run; text rendering only' } | ConvertTo-Json
