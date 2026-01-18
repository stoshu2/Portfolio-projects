<#
.SYNOPSIS
  Collects Windows Event Viewer logs (System + Application) and performance counters
  into a single output directory for troubleshooting and reporting.

.EXAMPLE
  .\collect.ps1 -Minutes 60 -OutDir C:\Temp\logreport_test

.EXAMPLE
  .\collect.ps1 -Minutes 120 -OutDir C:\Temp\logreport_test -IncludeEvtx
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [ValidateRange(1, 10080)]
    [int]$Minutes = 60,

    [Parameter(Mandatory = $true)]
    [string]$OutDir,

    [Parameter(Mandatory = $false)]
    [ValidateRange(10, 600)]
    [int]$SampleSeconds = 60,

    [Parameter(Mandatory = $false)]
    [ValidateRange(1, 10)]
    [int]$IntervalSeconds = 1,
    
    [Parameter(Mandatory = $false)]
    [ValidateNotNullOrEmpty()]
    [ValidateScript({
            foreach ($lvl in $_) {
                if ($lvl -notin 1, 2, 3, 4, 5) { throw "Levels must be 1..5 (1=Critical,2=Error,3=Warning,4=Information,5=Verbose)." }
            }
            $true
        })]
    [int[]]$Levels = @(1, 2, 3),


    [Parameter(Mandatory = $false)]
    [switch]$IncludeEvtx
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}

function New-DirectoryIfMissing($path) {
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
    }
}

function Export-EventsCsv {
    param(
        [Parameter(Mandatory = $true)][string]$LogName,
        [Parameter(Mandatory = $true)][datetime]$StartTime,
        [Parameter(Mandatory = $true)][string]$OutPath,
        [Parameter(Mandatory = $true)][int[]]$Levels
    )

    Write-Step "Collecting events: $LogName (since $StartTime) -> $OutPath"

    # Pull more than just Error/Critical—include Warning too.
    # Level: 1=Critical,2=Error,3=Warning,4=Information,5=Verbose
    $filter = @{
        LogName   = $LogName
        StartTime = $StartTime
    }

$events = @()
try {
  $events = Get-WinEvent -FilterHashtable $filter -ErrorAction Stop |
    Where-Object { $_.Level -in $Levels }
}
catch {
  # If there are simply no matching events, write an empty CSV (header only) and return
  if ($_.FullyQualifiedErrorId -like "*NoMatchingEventsFound*") {
    Write-Step "No matching events found for $LogName in this window. Writing empty CSV."
    "TimeCreated,LevelDisplayName,ProviderName,EventID,TaskDisplayName,MachineName,Message" |
      Out-File -Encoding UTF8 -FilePath $OutPath
    return
  }
  throw
}
 

    # Keep it CSV-friendly and useful
    if (-not $events -or $events.Count -eq 0) {
  Write-Step "No matching events after filtering for $LogName. Writing empty CSV."
  "TimeCreated,LevelDisplayName,ProviderName,EventID,TaskDisplayName,MachineName,Message" |
    Out-File -Encoding UTF8 -FilePath $OutPath
  return
}

    $events |
    Select-Object `
    @{n = "TimeCreated"; e = { $_.TimeCreated } },
    @{n = "LevelDisplayName"; e = { $_.LevelDisplayName } },
    @{n = "ProviderName"; e = { $_.ProviderName } },
    @{n = "EventID"; e = { $_.Id } },
    @{n = "TaskDisplayName"; e = { $_.TaskDisplayName } },
    @{n = "MachineName"; e = { $_.MachineName } },
    @{n = "Message"; e = { ($_.Message -replace "\r?\n", " ") } } |
    Export-Csv -NoTypeInformation -Encoding UTF8 -Path $OutPath
}

function Export-EventsEvtxFiltered {
    param(
        [Parameter(Mandatory = $true)][string]$LogName,
        [Parameter(Mandatory = $true)][int]$WindowMinutes,
        [Parameter(Mandatory = $true)][string]$OutPath
    )

    # Filter by "timediff(@SystemTime)" which is milliseconds from now.
    # This exports only events within the window.
    $ms = $WindowMinutes * 60 * 1000
    $query = "*[System[TimeCreated[timediff(@SystemTime) <= $ms]]]"

    Write-Step "Exporting EVTX (filtered): $LogName (last $WindowMinutes min) -> $OutPath"
    & wevtutil epl $LogName $OutPath "/q:$query" /ow:true | Out-Null
}

function Export-PerfCounters {
    param(
        [Parameter(Mandatory = $true)][int]$SampleSeconds,
        [Parameter(Mandatory = $true)][int]$IntervalSeconds,
        [Parameter(Mandatory = $true)][string]$SamplesOutPath,
        [Parameter(Mandatory = $true)][string]$SummaryOutPath
    )

    # Keep v1 simple and high-signal.
    $counters = @(
        '\Processor(_Total)\% Processor Time',
        '\Memory\% Committed Bytes In Use',
        '\Memory\Available MBytes',
        '\PhysicalDisk(_Total)\Avg. Disk Queue Length'
    )

    $maxSamples = [Math]::Ceiling($SampleSeconds / $IntervalSeconds)

    Write-Step "Sampling performance counters for $SampleSeconds sec (every $IntervalSeconds sec, $maxSamples samples)"
    $result = Get-Counter -Counter $counters -SampleInterval $IntervalSeconds -MaxSamples $maxSamples

    # Raw samples (tidy)
    $rows = foreach ($set in $result.CounterSamples | Group-Object { $_.TimeStamp }) {
        foreach ($sample in $set.Group) {
            [PSCustomObject]@{
                Timestamp = $sample.TimeStamp.ToString("o")
                Counter   = $sample.Path
                Value     = [Math]::Round([double]$sample.CookedValue, 3)
            }
        }
    }

    $rows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $SamplesOutPath

    # Summary (avg/max per counter)
    $summary = $rows |
    Group-Object Counter |
    ForEach-Object {
        $vals = $_.Group.Value
        [PSCustomObject]@{
            Counter = $_.Name
            Avg     = [Math]::Round((($vals | Measure-Object -Average).Average), 3)
            Max     = [Math]::Round((($vals | Measure-Object -Maximum).Maximum), 3)
            Samples = $vals.Count
        }
    }

    $summary | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $SummaryOutPath
}

function Export-SystemInfo {
    param(
        [Parameter(Mandatory = $true)][string]$OutPath
    )

    Write-Step "Collecting system info -> $OutPath"

    $os = Get-CimInstance Win32_OperatingSystem
    $cs = Get-CimInstance Win32_ComputerSystem

    $info = [PSCustomObject]@{
        Hostname      = $env:COMPUTERNAME
        Username      = $env:USERNAME
        Domain        = $env:USERDOMAIN
        OS            = $os.Caption
        OSVersion     = $os.Version
        BuildNumber   = $os.BuildNumber
        BootTime      = ($os.LastBootUpTime).ToString("o")
        TotalMemoryGB = [Math]::Round(($cs.TotalPhysicalMemory / 1GB), 2)
        Timestamp     = (Get-Date).ToString("o")
    }

    $info | ConvertTo-Json -Depth 4 | Out-File -Encoding UTF8 -FilePath $OutPath
}

# --- Main ---
New-DirectoryIfMissing $OutDir

$startTime = (Get-Date).AddMinutes(-$Minutes)

# Files
$sysInfoPath = Join-Path $OutDir "system_info.json"
$sysCsvPath = Join-Path $OutDir "events_system.csv"
$appCsvPath = Join-Path $OutDir "events_application.csv"
$perfSamplesPath = Join-Path $OutDir "perf_samples.csv"
$perfSummaryPath = Join-Path $OutDir "perf_summary.csv"

$sysEvtxPath = Join-Path $OutDir "System.evtx"
$appEvtxPath = Join-Path $OutDir "Application.evtx"

Write-Step "Output directory: $OutDir"
Write-Step "Time window: last $Minutes minutes (since $startTime)"
Write-Step "Event levels: $($Levels -join ', ') (1=Critical,2=Error,3=Warning,4=Information,5=Verbose)"

Export-SystemInfo -OutPath $sysInfoPath
Export-EventsCsv -LogName "System"      -StartTime $startTime -OutPath $sysCsvPath -Levels $Levels
Export-EventsCsv -LogName "Application" -StartTime $startTime -OutPath $appCsvPath -Levels $Levels

if ($IncludeEvtx) {
    Export-EventsEvtxFiltered -LogName "System"      -WindowMinutes $Minutes -OutPath $sysEvtxPath
    Export-EventsEvtxFiltered -LogName "Application" -WindowMinutes $Minutes -OutPath $appEvtxPath
}

Export-PerfCounters `
    -SampleSeconds $SampleSeconds `
    -IntervalSeconds $IntervalSeconds `
    -SamplesOutPath $perfSamplesPath `
    -SummaryOutPath $perfSummaryPath

Write-Step "Done."
Write-Step "Created:"
Write-Step "  $sysInfoPath"
Write-Step "  $sysCsvPath"
Write-Step "  $appCsvPath"
Write-Step "  $perfSamplesPath"
Write-Step "  $perfSummaryPath"
if ($IncludeEvtx) {
    Write-Step "  $sysEvtxPath"
    Write-Step "  $appEvtxPath"
}
