from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def esc(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def badge(status: str) -> str:
    cls = {"OK": "ok", "WARN": "warn", "ALERT": "bad"}.get(status, "ok")
    return f"<span class='badge {cls}'>{esc(status)}</span>"


def classify_disk(d: Dict[str, Any], t: Dict[str, Any]) -> Tuple[str, str]:
    pct = d.get("FreePercent")
    if pct is None:
        return "WARN", "No disk size/free data"
    if pct < t["disk_free_alert_pct"]:
        return "ALERT", f"Low disk space: {pct:.2f}% free"
    if pct < t["disk_free_warn_pct"]:
        return "WARN", f"Disk space getting low: {pct:.2f}% free"
    return "OK", "Disk space OK"


def ensure_list(x):
    # PowerShell ConvertTo-Json returns an object instead of an array when there's only 1 item
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def classify_resource(
    r: Dict[str, Any], t: Dict[str, Any]
) -> List[Tuple[str, str, str]]:
    out = []
    cpu = r.get("CpuLoadPercent")
    mem = r.get("MemoryUsedPercent")

    if cpu is not None:
        if cpu >= t["cpu_alert_pct"]:
            out.append(("ALERT", "CPU", f"High CPU load: {cpu:.2f}%"))
        elif cpu >= t["cpu_warn_pct"]:
            out.append(("WARN", "CPU", f"Elevated CPU load: {cpu:.2f}%"))
        else:
            out.append(("OK", "CPU", f"CPU load OK: {cpu:.2f}%"))
    else:
        out.append(("WARN", "CPU", "CPU load unavailable"))

    if mem is not None:
        if mem >= t["mem_used_alert_pct"]:
            out.append(("ALERT", "Memory", f"High memory usage: {mem:.2f}%"))
        elif mem >= t["mem_used_warn_pct"]:
            out.append(("WARN", "Memory", f"Elevated memory usage: {mem:.2f}%"))
        else:
            out.append(("OK", "Memory", f"Memory usage OK: {mem:.2f}%"))
    else:
        out.append(("WARN", "Memory", "Memory usage unavailable"))

    return out


def make_table(headers: List[str], rows: List[List[Any]]) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    if not rows:
        body = f"<tr><td colspan='{len(headers)}'><i>No data</i></td></tr>"
    else:
        body = "".join(
            "<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows
        )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def build_html(data: Dict[str, Any]) -> str:
    sysinfo = data["system_info"]
    thresholds = data["thresholds"]

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Summary counts
    alerts = [x for x in data["findings"] if x["status"] == "ALERT"]
    warns = [x for x in data["findings"] if x["status"] == "WARN"]

    summary = make_table(
        ["Host", "OS", "Uptime (hrs)", "Alerts", "Warnings", "Generated"],
        [
            [
                sysinfo.get("Hostname", ""),
                sysinfo.get("OS", ""),
                sysinfo.get("UptimeHours", ""),
                str(len(alerts)),
                str(len(warns)),
                generated,
            ]
        ],
    )

    findings_rows = [
        [badge(f["status"]), f["category"], f["message"]] for f in data["findings"]
    ]
    findings_tbl = make_table(["Status", "Category", "Details"], findings_rows)

    disks_tbl = make_table(
        ["Drive", "SizeGB", "FreeGB", "Free%", "Volume", "Status", "Notes"],
        [
            [
                d.get("Drive", ""),
                d.get("SizeGB", ""),
                d.get("FreeGB", ""),
                d.get("FreePercent", ""),
                d.get("VolumeName", ""),
                d.get("_status", ""),
                d.get("_note", ""),
            ]
            for d in data["disk"]
        ],
    )

    services_tbl = make_table(
        ["Name", "DisplayName", "State", "StartMode"],
        [
            [
                s.get("Name", ""),
                s.get("DisplayName", ""),
                s.get("State", ""),
                s.get("StartMode", ""),
            ]
            for s in data["auto_services_stopped"]
        ],
    )

    reboot = data["reboot"]
    reboot_line = (
        "Pending reboot: YES" if reboot.get("Pending") else "Pending reboot: No"
    )
    reboot_reasons = (
        ", ".join(reboot.get("Reasons", [])) if reboot.get("Reasons") else ""
    )

    defender = data["defender"]
    defender_tbl = make_table(
        ["Available", "RealTimeProtectionEnabled", "AntivirusEnabled", "Notes"],
        [
            [
                defender.get("Available"),
                defender.get("RealTimeProtectionEnabled"),
                defender.get("AntivirusEnabled"),
                defender.get("Notes"),
            ]
        ],
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Endpoint Health Report - {esc(sysinfo.get("Hostname", ""))}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; }}
    h1 {{ margin-bottom: 6px; }}
    .meta {{ color: #555; margin-bottom: 18px; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-weight: 700; font-size: 12px; }}
    .ok {{ background: #e9f7ef; }}
    .warn {{ background: #fff4e5; }}
    .bad {{ background: #fdecea; }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0 22px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; font-size: 14px; vertical-align: top; }}
    th {{ text-align: left; background: #f6f6f6; }}
    code {{ background: #f4f4f4; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Endpoint Health Report</h1>
  <div class="meta">
    <div><b>{esc(reboot_line)}</b> {esc(reboot_reasons)}</div>
    <div><b>Thresholds:</b> Disk warn {esc(thresholds["disk_free_warn_pct"])}% / alert {esc(thresholds["disk_free_alert_pct"])}%,
      CPU warn {esc(thresholds["cpu_warn_pct"])}% / alert {esc(thresholds["cpu_alert_pct"])}%,
      Mem warn {esc(thresholds["mem_used_warn_pct"])}% / alert {esc(thresholds["mem_used_alert_pct"])}%</div>
  </div>

  <h2>Summary</h2>
  {summary}

  <h2>Findings</h2>
  {findings_tbl}

  <h2>Disks</h2>
  {disks_tbl}

  <h2>Auto Services Stopped</h2>
  {services_tbl}

  <h2>Defender</h2>
  {defender_tbl}
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate endpoint health report from collect.ps1 outputs"
    )
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--thresholds", required=True)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    t = read_json(Path(args.thresholds))

    sysinfo = read_json(outdir / "system_info.json")
    disks = ensure_list(read_json(outdir / "disk.json"))
    resource = read_json(outdir / "resource.json")
    services = ensure_list(read_json(outdir / "services.json"))
    reboot = read_json(outdir / "reboot.json")
    defender = read_json(outdir / "defender.json")

    findings: List[Dict[str, str]] = []

    # Disk findings + annotate
    for d in disks:
        status, note = classify_disk(d, t)
        d["_status"] = status
        d["_note"] = note
        if status != "OK":
            findings.append(
                {
                    "status": status,
                    "category": f"Disk {d.get('Drive', '')}",
                    "message": note,
                }
            )

    # CPU/Mem findings
    for status, cat, msg in classify_resource(resource, t):
        if status != "OK":
            findings.append({"status": status, "category": cat, "message": msg})

    # Services findings (exclude allowlist)
    allow = set(x.lower() for x in t.get("service_allowlist", []))
    auto_stopped = []
    for s in services:
        name = (s.get("Name") or "").strip()
        if name.lower() in allow:
            continue
        auto_stopped.append(s)

    if auto_stopped:
        findings.append(
            {
                "status": "WARN",
                "category": "Services",
                "message": f"{len(auto_stopped)} Automatic service(s) not running",
            }
        )

    # Pending reboot
    if reboot.get("Pending"):
        findings.append(
            {
                "status": "WARN",
                "category": "Reboot",
                "message": "Pending reboot detected",
            }
        )

    # Defender
    if (
        defender.get("Available") is True
        and defender.get("RealTimeProtectionEnabled") is False
    ):
        findings.append(
            {
                "status": "WARN",
                "category": "Defender",
                "message": "Real-time protection is disabled",
            }
        )

    # Sort findings: ALERT first, then WARN
    order = {"ALERT": 0, "WARN": 1, "OK": 2}
    findings.sort(key=lambda x: order.get(x["status"], 9))

    report_obj = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "thresholds": t,
        "system_info": sysinfo,
        "disk": disks,
        "resource": resource,
        "auto_services_stopped": auto_stopped,
        "reboot": reboot,
        "defender": defender,
        "findings": findings,
    }

    (outdir / "report.json").write_text(
        json.dumps(report_obj, indent=2), encoding="utf-8"
    )
    (outdir / "report.html").write_text(build_html(report_obj), encoding="utf-8")

    print(f"Wrote: {outdir / 'report.html'}")
    print(f"Wrote: {outdir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# End of src/report.py
