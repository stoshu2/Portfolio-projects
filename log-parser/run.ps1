[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [ValidateRange(1, 10080)]
    [int]$Minutes = 60,

    [Parameter(Mandatory = $false)]
    [ValidateRange(10, 600)]
    [int]$SampleSeconds = 60,

    [Parameter(Mandatory = $false)]
    [ValidateRange(1, 10)]
    [int]$IntervalSeconds = 1,

    [Parameter(Mandatory = $false)]
    [int[]]$Levels = @(1, 2, 3),

    [Parameter(Mandatory = $false)]
    [string]$OutRoot = "C:\Temp",

    [Parameter(Mandatory = $false)]
    [string]$Ticket = "",

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

# --- Resolve paths relative to repo root ---
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$collectPs1 = Join-Path $repoRoot "src\collect.ps1"
$reportPy = Join-Path $repoRoot "src\report.py"

if (-not (Test-Path -LiteralPath $collectPs1)) { throw "Missing collector script: $collectPs1" }
if (-not (Test-Path -LiteralPath $reportPy)) { throw "Missing report script: $reportPy" }

# --- Output folder naming ---
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$computerName = $env:COMPUTERNAME
$prefix = if ([string]::IsNullOrWhiteSpace($Ticket)) { "logreport" } else { $Ticket.Trim() }
$outDirName = "{0}_{1}_{2}" -f $prefix, $computerName, $ts

New-DirectoryIfMissing $OutRoot
$outDir = Join-Path $OutRoot $outDirName
New-DirectoryIfMissing $outDir

Write-Step "Repo: $repoRoot"
Write-Step "Output: $outDir"
Write-Step "Window: last $Minutes minutes"
Write-Step "Perf sample: $SampleSeconds sec @ $IntervalSeconds sec interval"
Write-Step "Levels: $($Levels -join ',') (1=Critical,2=Error,3=Warning,4=Info,5=Verbose)"
Write-Step "Include EVTX: $IncludeEvtx"

# --- Run collection ---
Write-Step "Running collector..."

& $collectPs1 `
    -Minutes $Minutes `
    -OutDir $outDir `
    -SampleSeconds $SampleSeconds `
    -IntervalSeconds $IntervalSeconds `
    -Levels $Levels `
    -IncludeEvtx:$IncludeEvtx

if (-not $?) { throw "Collection failed." }



# --- Run report generation ---
Write-Step "Generating report..."
& python $reportPy --outdir $outDir --minutes $Minutes
if ($LASTEXITCODE -ne 0) { throw "Report generation failed with exit code $LASTEXITCODE" }


# --- Zip everything ---
$zipPath = Join-Path $OutRoot ("{0}.zip" -f $outDirName)
Write-Step "Creating zip: $zipPath"

if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }

Compress-Archive -Path (Join-Path $outDir "*") -DestinationPath $zipPath -Force

Write-Step "Done."
Write-Step "Folder: $outDir"
Write-Step "Zip:    $zipPath"
Write-Step "Report: $(Join-Path $outDir 'report.html')"
