param(
    [Parameter(Mandatory = $true)][string]$Directory,
    [switch]$TestOnly
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if (-not [IO.Path]::IsPathRooted($Directory) -or $Directory.StartsWith('\\')) { throw 'Use an explicit local absolute directory.' }
$full = [IO.Path]::GetFullPath($Directory)
$testRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.validation'))
$production = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'PhilosopherStoneCRM-ReleaseKeys'))
if ($TestOnly) {
    if (-not $full.StartsWith(($testRoot + '\key-test-'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Test keys must be in .validation/key-test-*.' }
} elseif (-not $full.Equals($production, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Production key location must be separately approved; expected the dedicated LocalAppData directory.'
}
if (Test-Path -LiteralPath $full) { throw 'Refusing any existing directory or files.' }
$parent = [IO.Path]::GetDirectoryName($full)
if (-not (Test-Path -LiteralPath $parent -PathType Container)) { throw 'Parent directory must already exist.' }
$current = Get-Item -LiteralPath $parent
while ($null -ne $current) {
    if (($current.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Key directory ancestors cannot be links.' }
    $current = $current.Parent
}
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = [Security.AccessControl.DirectorySecurity]::new()
$acl.SetAccessRuleProtection($true, $false)
$acl.SetOwner($sid)
$inherit = [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
$propagation = [Security.AccessControl.PropagationFlags]::None
foreach ($principal in @($sid, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($principal, 'FullControl', $inherit, $propagation, 'Allow'))
}
New-Item -ItemType Directory -Path $full | Out-Null
Set-Acl -LiteralPath $full -AclObject $acl
& node (Join-Path $PSScriptRoot 'release-tools.cjs') generate $full
if ($LASTEXITCODE -ne 0) { throw 'Key generation refused; existing files have not been overwritten.' }
