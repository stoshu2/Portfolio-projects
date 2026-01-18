Log Parser & Performance Report Tool

A Windows troubleshooting tool that collects Event Viewer logs and performance counters, then generates a structured HTML and JSON report for fast analysis.

Built using PowerShell (collection) and Python (reporting) to mirror real-world IT automation workflows.

Features

Collects Windows Event Viewer logs:

System

Application

Configurable severity levels (Critical / Error / Warning, etc.)

Samples performance counters:

CPU usage

Memory usage

Available memory

Disk queue length

Generates:

report.html (human-friendly)

report.json (machine-readable)

Packages everything into a single ZIP file

Designed for junior tech usability (one command)

Folder Structure
Log_Parser/
│  run.ps1
│  README.md
│
|_ src/
   │  collect.ps1
   │  report.py

Requirements

Windows 10/11 or Windows Server

PowerShell 5.1+ or PowerShell Core

Python 3.10+

Python must be available in PATH
Verify with: python --version

Quick Start

From the project root:

.\run.ps1 -Minutes 30 -Ticket INC12345 -OutRoot C:\Temp

What this does

Collects logs from the last 30 minutes

Samples performance counters for 60 seconds

Creates an output folder:

C:\Temp\INC12345_HOSTNAME_TIMESTAMP\


Generates:

report.html

report.json

Creates a ZIP:

C:\Temp\INC12345_HOSTNAME_TIMESTAMP.zip

Common Examples
Basic run
.\run.ps1 -Minutes 60

With ticket number
.\run.ps1 -Minutes 30 -Ticket INC56789

Include EVTX exports
.\run.ps1 -Minutes 30 -IncludeEvtx

Change severity levels
# Only Critical + Error
.\run.ps1 -Levels 1,2


Severity mapping:

Level	Meaning
1	Critical
2	Error
3	Warning
4	Information
5	Verbose
Output Files

Inside the generated folder:

system_info.json

events_system.csv

events_application.csv

perf_samples.csv

perf_summary.csv

report.html

report.json

(optional) System.evtx

(optional) Application.evtx

Why This Tool Exists

This tool was built to simulate real-world IT support workflows:

Junior tech pulls logs

Packages everything quickly

Leaves customer working

Reviews report later

Attaches ZIP to ticket

Safety

Read-only

Does not modify system settings

Does not install software

Only reads logs and counters

Future Improvements

Charting (CPU/memory over time)

Additional log channels

Redaction option (usernames/IPs)

GUI wrapper

Standalone EXE build

Author

Nathen Wetherbee
Portfolio project – Windows automation & reporting