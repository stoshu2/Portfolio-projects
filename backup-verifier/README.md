# Backup Verification Tool

A reporting tool that verifies backup job health by identifying failed, warning, and stale backups based on configurable thresholds.

Built to automate daily backup checks commonly performed by IT support and MSP technicians.

---

## Overview

This tool reads a standardized backup job CSV, evaluates job status and recency, and generates a clear HTML and JSON report highlighting issues that require attention.

The default configuration marks backups as **stale after 3 days since the last successful run**, reflecting real-world environments with large datasets.

---

## Features

- Evaluates backup jobs for:
  - Failed runs
  - Warning states
  - Stale backups (configurable threshold)
- Generates:
  - `report.html` (human-readable)
  - `report.json` (machine-readable)
- Produces a timestamped output folder
- Packages results into a ZIP for easy ticket attachment
- Includes sample data for immediate demo use

---

## Folder Structure

backup-verifier/
│ run.ps1
│ README.md
│
└─ src/
│ report.py
│ thresholds.json
│
└─ samples/
jobs_sample.csv


---

## Requirements

- Windows
- PowerShell 5.1+ or PowerShell Core
- Python 3.10+

---

## Quick Start (Sample Data)

From the `backup-verifier` folder:

```powershell
.\run.ps1 -Ticket TESTBACKUP -OutRoot C:\Temp

This will:

Analyze the included sample CSV

Generate a report folder

Create a ZIP bundle

Print output paths to the console


Input CSV Format
The tool expects a CSV with the following columns:
job_name
last_run
last_result
last_success
duration_minutes
notes
Dates should be ISO-formatted (e.g. 2026-01-17T02:10:00).

Why This Tool Exists

This project was inspired by real-world experience manually verifying backups across multiple clients each morning. Automating this process saves time, reduces missed failures, and produces consistent reporting.

Future Improvements

Native parsers for backup platforms (Veeam, Datto, etc.)

Multi-client aggregation

Trend analysis on backup duration

Email or ticketing integration

Author
Nathen Wetherbee
Portfolio project – IT automation & reporting