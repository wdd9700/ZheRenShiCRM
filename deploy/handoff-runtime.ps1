param(
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$SourceEnv,
    [Parameter(Mandatory = $true)][string]$TargetDir,
    [switch]$SecureRuntimeDir
)

$ErrorActionPreference = 'Stop'
$stage = 'preflight'
try {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $trusted = @($identity.User.Value, 'S-1-5-18', 'S-1-5-32-544')

    function Assert-LocalPath([string]$Path) {
        $full = [System.IO.Path]::GetFullPath($Path)
        $drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($full))
        if ($drive.DriveType -ne [System.IO.DriveType]::Fixed) {
            throw 'Only a local fixed drive is supported'
        }
        $node = $full
        while ($node) {
            if (Test-Path -LiteralPath $node) {
                $item = Get-Item -LiteralPath $node -Force
                if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                    throw 'Reparse points are not permitted'
                }
            }
            $parent = [System.IO.Directory]::GetParent($node)
            $node = if ($parent) { $parent.FullName } else { $null }
        }
    }

    function Assert-Owner([string]$Path) {
        $acl = Get-Acl -LiteralPath $Path
        if ($acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -notin $trusted) {
            throw 'Untrusted destination owner'
        }
    }

    function Assert-Private([string]$Path) {
        Assert-Owner $Path
        $acl = Get-Acl -LiteralPath $Path
        if (-not $acl.AreAccessRulesProtected) {
            throw 'Destination ACL inheritance must be disabled'
        }
        foreach ($rule in $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) {
            if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin $trusted) {
                throw 'Destination ACL permits another principal'
            }
        }
    }

    function New-PrivateAcl([bool]$Directory) {
        $acl = if ($Directory) {
            [System.Security.AccessControl.DirectorySecurity]::new()
        } else {
            [System.Security.AccessControl.FileSecurity]::new()
        }
        $acl.SetOwner($identity.User)
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($sid in $trusted) {
            $principal = [System.Security.Principal.SecurityIdentifier]::new($sid)
            $rule = if ($Directory) {
                [System.Security.AccessControl.FileSystemAccessRule]::new(
                    $principal, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'
                )
            } else {
                [System.Security.AccessControl.FileSystemAccessRule]::new($principal, 'FullControl', 'Allow')
            }
            $acl.AddAccessRule($rule)
        }
        return $acl
    }

    function Get-PrivateDigest([string]$Path) {
        $stream = [System.IO.File]::Open($Path, 'Open', 'Read', 'Read')
        $hash = [System.Security.Cryptography.SHA256]::Create()
        try { return [System.Convert]::ToBase64String($hash.ComputeHash($stream)) }
        finally { $hash.Dispose(); $stream.Dispose() }
    }

    $sources = @{
        '.env' = $SourceEnv
        'image.env' = (Join-Path $SourceDir '.runtime\image.env')
    }
    $runtime = Join-Path $TargetDir '.runtime'
    $digests = @{}
    foreach ($base in @($SourceDir, $TargetDir, $runtime)) { Assert-LocalPath $base }
    Assert-Owner $TargetDir
    $parentAcl = Get-Acl -LiteralPath $TargetDir
    foreach ($rule in $parentAcl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -eq 'Allow' -and
            $rule.IdentityReference.Value -notin $trusted -and
            -not ($rule.PropagationFlags -band [System.Security.AccessControl.PropagationFlags]::InheritOnly) -and
            ([long]$rule.FileSystemRights -band 0x100C0040)) {
            throw 'Parent ACL permits replacement of the private runtime directory'
        }
    }
    if (Test-Path -LiteralPath (Join-Path $TargetDir '.env')) {
        throw 'Legacy destination .env requires explicit reconciliation first'
    }
    foreach ($relative in $sources.Keys) {
        $source = $sources[$relative]
        $target = Join-Path $runtime $relative
        Assert-LocalPath $source
        Assert-LocalPath $target
        if (-not [System.IO.File]::Exists($source) -or (Get-Item -LiteralPath $source -Force).Length -gt 65536) {
            throw 'Source runtime file missing or invalid'
        }
        $digests[$relative] = Get-PrivateDigest $source
        if (Test-Path -LiteralPath $target) {
            if (-not [System.IO.File]::Exists($target)) { throw 'Destination is not a regular file' }
            Assert-Private $target
            if ((Get-PrivateDigest $target) -ne $digests[$relative]) {
                throw 'Destination runtime file differs; refusing overwrite'
            }
        }
    }

    if (Test-Path -LiteralPath $runtime) {
        if (-not [System.IO.Directory]::Exists($runtime)) { throw 'Invalid destination runtime directory' }
        Assert-Owner $runtime
        if ($SecureRuntimeDir) {
            $stage = 'secure-runtime-directory-acl'
            Set-Acl -LiteralPath $runtime -AclObject (New-PrivateAcl $true)
        }
    } else {
        [void][System.IO.Directory]::CreateDirectory($runtime, (New-PrivateAcl $true))
    }
    Assert-Private $runtime

    $stage = 'copy-runtime-files'
    foreach ($relative in $sources.Keys) {
        $source = $sources[$relative]
        $target = Join-Path $runtime $relative
        if (-not [System.IO.File]::Exists($target)) {
            $inputStream = [System.IO.File]::Open($source, 'Open', 'Read', 'Read')
            $outputStream = $null
            try {
                $outputStream = [System.IO.FileStream]::new(
                    $target, [System.IO.FileMode]::CreateNew,
                    [System.Security.AccessControl.FileSystemRights]::Write,
                    [System.IO.FileShare]::None, 4096, [System.IO.FileOptions]::WriteThrough,
                    (New-PrivateAcl $false)
                )
                $inputStream.CopyTo($outputStream)
                $outputStream.Flush($true)
            } finally {
                if ($outputStream) { $outputStream.Dispose() }
                $inputStream.Dispose()
            }
        }
        Assert-Private $target
        if ((Get-PrivateDigest $target) -ne $digests[$relative] -or (Get-PrivateDigest $source) -ne $digests[$relative]) {
            throw 'Runtime bytes changed; keep both copies for investigation'
        }
    }
    Write-Output 'PASS: private local runtime copies match; source files retained'
    exit 0
} catch {
    [Console]::Error.WriteLine("Runtime handoff failed at $stage; no source files removed, no existing file overwritten; retain partial destination for investigation")
    exit 1
}
