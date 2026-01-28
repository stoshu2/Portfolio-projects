[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutDir
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}
function New-DirectoryIfNotExists($path) {
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
    }
}

New-DirectoryIfNotExists $OutDir

# --- System info ---
Write-Step "Collecting system info..."
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$boot = $os.LastBootUpTime
$now = Get-Date
$uptime = New-TimeSpan -Start $boot -End $now

$system = [PSCustomObject]@{
    Hostname    = $env:COMPUTERNAME
    Username    = $env:USERNAME
    Domain      = $env:USERDOMAIN
    OS          = $os.Caption
    OSVersion   = $os.Version
    BuildNumber = $os.BuildNumber
    BootTime    = ($boot).ToString("o")
    UptimeHours = [Math]::Round($uptime.TotalHours, 2)
    Timestamp   = ($now).ToString("o")
}
$system | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 -Path (Join-Path $OutDir "system_info.json")

# --- Disk info ---
Write-Step "Collecting disk info..."
$disks = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
    $size = [double]$_.Size
    $free = [double]$_.FreeSpace
    $freePct = if ($size -gt 0) { ($free / $size) * 100.0 } else { $null }

    [PSCustomObject]@{
        Drive       = $_.DeviceID
        SizeGB      = [Math]::Round($size / 1GB, 2)
        FreeGB      = [Math]::Round($free / 1GB, 2)
        FreePercent = if ($null -ne $freePct) { [Math]::Round($freePct, 2) } else { $null }
        VolumeName  = $_.VolumeName
    }
}
$disks | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 -Path (Join-Path $OutDir "disk.json")

# --- CPU + Memory snapshot ---
Write-Step "Collecting resource snapshot..."
$cpuLoad = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$memTotal = [double]$cs.TotalPhysicalMemory
$memFree = [double]$os.FreePhysicalMemory * 1KB  # FreePhysicalMemory is in KB
$memUsed = $memTotal - $memFree
$memUsedPct = if ($memTotal -gt 0) { ($memUsed / $memTotal) * 100.0 } else { $null }

$resource = [PSCustomObject]@{
    CpuLoadPercent    = [Math]::Round([double]$cpuLoad, 2)
    MemoryTotalGB     = [Math]::Round($memTotal / 1GB, 2)
    MemoryUsedGB      = [Math]::Round($memUsed / 1GB, 2)
    MemoryUsedPercent = if ($null -ne $memUsedPct) { [Math]::Round($memUsedPct, 2) } else { $null }
}
$resource | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 -Path (Join-Path $OutDir "resource.json")

# --- Services: Automatic but stopped ---
Write-Step "Collecting service status..."
$autoStopped = Get-CimInstance Win32_Service |
Where-Object { $_.StartMode -eq "Auto" -and $_.State -ne "Running" } |
Select-Object Name, DisplayName, State, StartMode

$autoStopped | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 -Path (Join-Path $OutDir "services.json")

# --- Pending reboot check (best effort) ---
Write-Step "Checking pending reboot..."
$reboot = [ordered]@{
    Pending = $false
    Reasons = @()
}

# Common reboot indicators
$pathsToCheck = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"
)

foreach ($p in $pathsToCheck) {
    if (Test-Path $p) {
        $reboot.Pending = $true
        $reboot.Reasons += $p
    }
}

# PendingFileRenameOperations
try {
    $pfo = Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager" -Name "PendingFileRenameOperations" -ErrorAction SilentlyContinue
    if ($pfo -and $pfo.PendingFileRenameOperations) {
        $reboot.Pending = $true
        $reboot.Reasons += "PendingFileRenameOperations"
    }
}
catch {}

([PSCustomObject]$reboot) | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 -Path (Join-Path $OutDir "reboot.json")

# --- Defender status (best effort; won’t fail tool) ---
Write-Step "Collecting Defender status (best effort)..."
$def = [ordered]@{
    Available                 = $false
    RealTimeProtectionEnabled = $null
    AntivirusEnabled          = $null
    Notes                     = ""
}

try {
    if (Get-Command Get-MpComputerStatus -ErrorAction SilentlyContinue) {
        $s = Get-MpComputerStatus
        $def.Available = $true
        $def.RealTimeProtectionEnabled = $s.RealTimeProtectionEnabled
        $def.AntivirusEnabled = $s.AntivirusEnabled
    }
    else {
        $def.Notes = "Get-MpComputerStatus not available on this system."
    }
}
catch {
    $def.Notes = $_.Exception.Message
}

([PSCustomObject]$def) | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 -Path (Join-Path $OutDir "defender.json")

Write-Step "Collection complete."
Exit 0