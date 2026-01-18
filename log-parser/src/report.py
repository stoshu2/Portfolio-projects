from __future__ import annotations

import argparse
import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def normalize_counter_path(raw: str) -> str:
    """
    Turns \\HOST\\processor(_total)\\% processor time
    into  \\processor(_total)\\% processor time
    and lowercases for stable matching.
    """
    s = raw.strip()
    m = re.match(r"^\\\\[^\\]+\\(.*)$", s)
    if m:
        s = "\\" + m.group(1)
    return s.lower()


def friendly_counter_name(norm: str) -> str:
    # Keep it simple: title-case common ones for display
    mapping = {
        r"\processor(_total)\% processor time": "CPU % Processor Time (Total)",
        r"\memory\% committed bytes in use": "Memory % Committed Bytes In Use",
        r"\memory\available mbytes": "Memory Available MB",
        r"\physicaldisk(_total)\avg. disk queue length": "Disk Avg. Disk Queue Length (Total)",
    }
    return mapping.get(norm, norm)


def classify_perf(norm: str, avg: float, maxv: float) -> Tuple[str, str]:
    """
    Returns (status, reason). Status in: OK / WARN / ALERT
    """
    # Simple, credible defaults (tune later or move to thresholds.json)
    thresholds = {
        r"\processor(_total)\% processor time": {"warn": 70.0, "alert": 85.0},
        r"\memory\% committed bytes in use": {"warn": 75.0, "alert": 85.0},
        r"\physicaldisk(_total)\avg. disk queue length": {"warn": 2.0, "alert": 4.0},
        # Available MB is inverse (low is bad)
        r"\memory\available mbytes": {"warn_low": 1024.0, "alert_low": 512.0},
    }

    t = thresholds.get(norm)
    if not t:
        return "OK", "No threshold set"

    # Low-is-bad metric
    if "warn_low" in t:
        if maxv <= t["alert_low"] or avg <= t["alert_low"]:
            return "ALERT", f"Low available memory (avg={avg:.1f} MB, max={maxv:.1f} MB)"
        if maxv <= t["warn_low"] or avg <= t["warn_low"]:
            return "WARN", f"Low available memory (avg={avg:.1f} MB, max={maxv:.1f} MB)"
        return "OK", "Within normal range"

    # High-is-bad metrics
    if maxv >= t["alert"] or avg >= t["alert"]:
        return "ALERT", f"High usage (avg={avg:.1f}, max={maxv:.1f})"
    if maxv >= t["warn"] or avg >= t["warn"]:
        return "WARN", f"Elevated usage (avg={avg:.1f}, max={maxv:.1f})"
    return "OK", "Within normal range"


def read_perf_summary(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            raw = r.get("Counter", "") or ""
            avg = float(r.get("Avg", "0") or 0)
            maxv = float(r.get("Max", "0") or 0)
            samples = int(float(r.get("Samples", "0") or 0))
            norm = normalize_counter_path(raw)
            status, reason = classify_perf(norm, avg, maxv)
            rows.append(
                {
                    "counter_raw": raw,
                    "counter_norm": norm,
                    "counter_name": friendly_counter_name(norm),
                    "avg": avg,
                    "max": maxv,
                    "samples": samples,
                    "status": status,
                    "reason": reason,
                }
            )
    return rows


def read_events_csv(path: Path) -> List[Dict[str, str]]:
    # Your CSV headers: TimeCreated,LevelDisplayName,ProviderName,EventID,TaskDisplayName,MachineName,Message
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def count_by_level(events: List[Dict[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for e in events:
        lvl = (e.get("LevelDisplayName") or "").strip() or "Unknown"
        counts[lvl] = counts.get(lvl, 0) + 1
    return counts


def newest_events(events: List[Dict[str, str]], limit: int = 20) -> List[Dict[str, str]]:
    # TimeCreated is usually parseable by datetime.fromisoformat, but may vary.
    # We'll sort by string if parsing fails—good enough for v1.
    def key(e: Dict[str, str]) -> str:
        return (e.get("TimeCreated") or "").strip()

    return sorted(events, key=key, reverse=True)[:limit]


def esc(s: Any) -> str:
    return html.escape("" if s is None else str(s))


def make_table(headers: List[str], rows: List[List[Any]]) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    tr_parts = []
    for r in rows:
        tds = "".join(f"<td>{esc(c)}</td>" for c in r)
        tr_parts.append(f"<tr>{tds}</tr>")
    body = "".join(tr_parts) if tr_parts else f"<tr><td colspan='{len(headers)}'><i>No data</i></td></tr>"
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def status_badge(status: str) -> str:
    cls = {"OK": "ok", "WARN": "warn", "ALERT": "bad"}.get(status, "ok")
    return f"<span class='badge {cls}'>{esc(status)}</span>"


def build_html(
    sysinfo: Dict[str, Any],
    perf: List[Dict[str, Any]],
    sys_events: List[Dict[str, str]],
    app_events: List[Dict[str, str]],
    window_minutes: int,
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Alerts section
    alerts = [p for p in perf if p["status"] in ("WARN", "ALERT")]
    if alerts:
        alerts_html = "<ul>" + "".join(
            f"<li>{status_badge(a['status'])} <b>{esc(a['counter_name'])}</b>: {esc(a['reason'])}</li>"
            for a in alerts
        ) + "</ul>"
    else:
        alerts_html = "<p><span class='badge ok'>OK</span> No performance thresholds were exceeded.</p>"

    # Perf table
    perf_rows = []
    for p in perf:
        perf_rows.append([
            p["counter_name"],
            f"{p['avg']:.3f}",
            f"{p['max']:.3f}",
            str(p["samples"]),
            p["status"],
            p["reason"],
        ])
    perf_table = make_table(
        ["Counter", "Avg", "Max", "Samples", "Status", "Notes"],
        perf_rows
    )

    # Event summaries
    sys_counts = count_by_level(sys_events)
    app_counts = count_by_level(app_events)
    events_summary = make_table(
        ["Log", "Critical", "Error", "Warning", "Information", "Other/Unknown", "Total"],
        [
            [
                "System",
                str(sys_counts.get("Critical", 0)),
                str(sys_counts.get("Error", 0)),
                str(sys_counts.get("Warning", 0)),
                str(sys_counts.get("Information", 0)),
                str(sum(v for k, v in sys_counts.items() if k not in ("Critical", "Error", "Warning", "Information"))),
                str(len(sys_events)),
            ],
            [
                "Application",
                str(app_counts.get("Critical", 0)),
                str(app_counts.get("Error", 0)),
                str(app_counts.get("Warning", 0)),
                str(app_counts.get("Information", 0)),
                str(sum(v for k, v in app_counts.items() if k not in ("Critical", "Error", "Warning", "Information"))),
                str(len(app_events)),
            ],
        ],
    )

    # Newest events (only show noisy ones typically)
    newest_sys = newest_events([e for e in sys_events if (e.get("LevelDisplayName") or "") in ("Critical", "Error", "Warning")], 20)
    newest_app = newest_events([e for e in app_events if (e.get("LevelDisplayName") or "") in ("Critical", "Error", "Warning")], 20)

    def event_rows(events: List[Dict[str, str]]) -> List[List[Any]]:
        rows = []
        for e in events:
            rows.append([
                e.get("TimeCreated", ""),
                e.get("LevelDisplayName", ""),
                e.get("ProviderName", ""),
                e.get("EventID", ""),
                (e.get("Message", "") or "")[:200] + ("..." if (e.get("Message", "") or "") and len(e.get("Message", "")) > 200 else ""),
            ])
        return rows

    newest_sys_tbl = make_table(["Time", "Level", "Provider", "EventID", "Message (truncated)"], event_rows(newest_sys))
    newest_app_tbl = make_table(["Time", "Level", "Provider", "EventID", "Message (truncated)"], event_rows(newest_app))

    host = sysinfo.get("Hostname") or "Unknown"
    osname = sysinfo.get("OS") or "Unknown"
    boot = sysinfo.get("BootTime") or "Unknown"

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Log Report - {esc(host)}</title>
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
  <h1>Log Report</h1>
  <div class="meta">
    <div><b>Host:</b> {esc(host)}</div>
    <div><b>OS:</b> {esc(osname)}</div>
    <div><b>Boot Time:</b> {esc(boot)}</div>
    <div><b>Window:</b> Last {window_minutes} minutes</div>
    <div><b>Generated:</b> {esc(generated_at)}</div>
  </div>

  <h2>Alerts</h2>
  {alerts_html}

  <h2>Performance Summary</h2>
  {perf_table}

  <h2>Event Summary</h2>
  {events_summary}

  <h2>Newest System (Critical/Error/Warning)</h2>
  {newest_sys_tbl}

  <h2>Newest Application (Critical/Error/Warning)</h2>
  {newest_app_tbl}
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate an HTML report from collect.ps1 outputs")
    ap.add_argument("--outdir", required=True, help="Folder containing system_info.json, perf_summary.csv, events_*.csv")
    ap.add_argument("--minutes", type=int, default=60, help="Time window minutes (for display only)")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    sysinfo_path = outdir / "system_info.json"
    perf_path = outdir / "perf_summary.csv"
    sys_events_path = outdir / "events_system.csv"
    app_events_path = outdir / "events_application.csv"

    if not sysinfo_path.exists():
        raise FileNotFoundError(f"Missing {sysinfo_path}")
    if not perf_path.exists():
        raise FileNotFoundError(f"Missing {perf_path}")

    sysinfo = json.loads(sysinfo_path.read_text(encoding="utf-8-sig"))
    perf = read_perf_summary(perf_path)
    sys_events = read_events_csv(sys_events_path)
    app_events = read_events_csv(app_events_path)

    report_html = build_html(sysinfo, perf, sys_events, app_events, window_minutes=args.minutes)

    html_path = outdir / "report.html"
    html_path.write_text(report_html, encoding="utf-8")

    # Optional machine-readable output
    report_json = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window_minutes": args.minutes,
        "system_info": sysinfo,
        "perf": perf,
        "event_counts": {
            "system": count_by_level(sys_events),
            "application": count_by_level(app_events),
        },
    }
    (outdir / "report.json").write_text(json.dumps(report_json, indent=2), encoding="utf-8")

    print(f"Wrote: {html_path}")
    print(f"Wrote: {outdir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
