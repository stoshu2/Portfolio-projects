[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$OutRoot = "C:\Temp",

    [Parameter(Mandatory = $false)]
    [string]$Ticket = "",

    [Parameter(Mandatory = $false)]
    [string]$InputCsv = "",

    [Parameter(Mandatory = $false)]
    [string]$Thresholds = ""
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}
function Ensure-Dir($path) {
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
    }
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$reportPy = Join-Path $repoRoot "src\report.py"

# Defaults (sample mode)
if ([string]::IsNullOrWhiteSpace($InputCsv)) {
    $InputCsv = Join-Path $repoRoot "src\samples\jobs_sample.csv"
}
if ([string]::IsNullOrWhiteSpace($Thresholds)) {
    $Thresholds = Join-Path $repoRoot "src\thresholds.json"
}

if (-not (Test-Path -LiteralPath $reportPy)) { throw "Missing: $reportPy" }
if (-not (Test-Path -LiteralPath $InputCsv)) { throw "Missing: $InputCsv" }
if (-not (Test-Path -LiteralPath $Thresholds)) { throw "Missing: $Thresholds" }

Ensure-Dir $OutRoot

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$hostname = $env:COMPUTERNAME
$prefix = if ([string]::IsNullOrWhiteSpace($Ticket)) { "backupverify" } else { $Ticket.Trim() }
$outDirName = "{0}_{1}_{2}" -f $prefix, $hostname, $ts

$outDir = Join-Path $OutRoot $outDirName
Ensure-Dir $outDir

Write-Step "Repo: $repoRoot"
Write-Step "Input CSV: $InputCsv"
Write-Step "Thresholds: $Thresholds"
Write-Step "Output: $outDir"

& python $reportPy --input $InputCsv --thresholds $Thresholds --outdir $outDir
if ($LASTEXITCODE -ne 0) { throw "Report generation failed with exit code $LASTEXITCODE" }

$zipPath = Join-Path $OutRoot ("{0}.zip" -f $outDirName)
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }

Write-Step "Creating zip: $zipPath"
Compress-Archive -Path (Join-Path $outDir "*") -DestinationPath $zipPath -Force

Write-Step "Done."
Write-Step "Folder: $outDir"
Write-Step "Zip:    $zipPath"
Write-Step "Report: $(Join-Path $outDir 'report.html')"
exit 0