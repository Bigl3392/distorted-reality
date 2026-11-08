[CmdletBinding()]
param([switch]$WriteFiles)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) {
    $shell = Get-Command pwsh -ErrorAction Stop
    & $shell.Source -NoProfile -File $PSCommandPath @PSBoundParameters
    exit $LASTEXITCODE
}
try {
    $templatePath = Read-Host 'Absolute template directory'
    $expectedHash = Read-Host 'Expected SHA-256 of the sorted template hash manifest'
    $destination = Read-Host 'Absolute NEW destination directory (dry-run does not create it)'
    if (-not [IO.Path]::IsPathRooted($templatePath) -or -not [IO.Path]::IsPathRooted($destination)) { throw 'Absolute paths required' }
    if (Test-Path -LiteralPath $destination) { throw 'Destination already exists; refusing overwrite' }
    $templates = Get-ChildItem -LiteralPath $templatePath -File | Where-Object Name -Match '\.in($|\.sh$)' | Sort-Object Name
    if (-not $templates) { throw 'No templates found' }
    $manifest = ($templates | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower() + '  ' + $_.Name }) -join "`n"
    $actualHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($manifest))).ToLower()
    if ($expectedHash -cne $actualHash) { throw 'Template manifest hash mismatch' }
    $values = @{}
    $rendered = @{}
    foreach ($template in $templates) {
        $content = [IO.File]::ReadAllText($template.FullName)
        foreach ($match in [regex]::Matches($content, '<<([A-Z0-9_]+)>>')) {
            $name = $match.Groups[1].Value
            if (-not $values.ContainsKey($name)) {
                $value = Read-Host ("Reviewed non-secret value for " + $name)
                if (-not $value -or $value -eq 'UNSET' -or $value.Contains('<<') -or $value.Contains("`n") -or $value.Contains("`r")) { throw 'Unresolved or multiline value refused' }
                # Restrict substitutions to simple names, addresses, versions and absolute paths.
                if ($value -notmatch '^[a-zA-Z0-9_./:@+,-]+$') { throw 'Unsupported substitution character' }
                $values[$name] = $value
            }
            $content = $content.Replace($match.Value, $values[$name])
        }
        if ($content -match '<<[A-Z0-9_]+>>') { throw 'Unresolved placeholder' }
        $name = $template.Name -replace '\.in(?=\.sh$|$)', ''
        $rendered[$name] = $content
        Write-Output ("PREVIEW " + $name + "`n" + $content)
    }
    if ($WriteFiles) {
        [IO.Directory]::CreateDirectory($destination) | Out-Null
        foreach ($name in $rendered.Keys) {
            $stream = [IO.File]::Open((Join-Path $destination $name), [IO.FileMode]::CreateNew)
            try { $bytes = [Text.UTF8Encoding]::new($false).GetBytes($rendered[$name]); $stream.Write($bytes,0,$bytes.Length) }
            finally { $stream.Dispose() }
        }
    } else { Write-Output 'DRY RUN: no files written and no host contacted' }
} finally { Read-Host 'Press Enter to close' | Out-Null }
