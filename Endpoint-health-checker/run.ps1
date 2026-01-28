[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$OutRoot = "C:\Temp",

    [Parameter(Mandatory = $false)]
    [string]$Ticket = ""
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

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$collectPs1 = Join-Path $repoRoot "src\collect.ps1"
$reportPy = Join-Path $repoRoot "src\report.py"
$thresholds = Join-Path $repoRoot "src\thresholds.json"

if (-not (Test-Path -LiteralPath $collectPs1)) { throw "Missing: $collectPs1" }
if (-not (Test-Path -LiteralPath $reportPy)) { throw "Missing: $reportPy" }
if (-not (Test-Path -LiteralPath $thresholds)) { throw "Missing: $thresholds" }

New-DirectoryIfMissing $OutRoot

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$hostname = $env:COMPUTERNAME
$prefix = if ([string]::IsNullOrWhiteSpace($Ticket)) { "healthcheck" } else { $Ticket.Trim() }
$outDirName = "{0}_{1}_{2}" -f $prefix, $hostname, $ts

$outDir = Join-Path $OutRoot $outDirName
New-DirectoryIfMissing $outDir

Write-Step "Repo: $repoRoot"
Write-Step "Output: $outDir"

# Run collector in current session (keeps errors clean)
& $collectPs1 -OutDir $outDir
if (-not $?) { throw "Collector failed." }

# Generate report
& python $reportPy --outdir $outDir --thresholds $thresholds
if ($LASTEXITCODE -ne 0) { throw "Report generation failed with exit code $LASTEXITCODE" }

# Zip bundle
$zipPath = Join-Path $OutRoot ("{0}.zip" -f $outDirName)
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }

Write-Step "Creating zip: $zipPath"
Compress-Archive -Path (Join-Path $outDir "*") -DestinationPath $zipPath -Force

Write-Step "Done."
Write-Step "Folder: $outDir"
Write-Step "Zip:    $zipPath"
Write-Step "Report: $(Join-Path $outDir 'report.html')"
Exit 0