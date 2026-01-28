from __future__ import annotations

import argparse
import csv
import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def parse_dt(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    # Accept ISO-ish strings like 2026-01-17T02:10:00
    try:
        dt = datetime.fromisoformat(s)
        # treat naive as local; for comparisons use naive consistently
        return dt
    except Exception:
        return None


def days_since(dt: Optional[datetime], now: datetime) -> Optional[float]:
    if dt is None:
        return None
    delta = now - dt
    return delta.total_seconds() / 86400.0


@dataclass
class Job:
    job_name: str
    last_run: Optional[datetime]
    last_result: str
    last_success: Optional[datetime]
    duration_minutes: Optional[float]
    notes: str

    @staticmethod
    def from_row(r: Dict[str, str]) -> "Job":
        dur_raw = (r.get("duration_minutes") or "").strip()
        dur = None
        if dur_raw:
            try:
                dur = float(dur_raw)
            except Exception:
                dur = None

        return Job(
            job_name=(r.get("job_name") or "").strip(),
            last_run=parse_dt(r.get("last_run") or ""),
            last_result=(r.get("last_result") or "").strip(),
            last_success=parse_dt(r.get("last_success") or ""),
            duration_minutes=dur,
            notes=(r.get("notes") or "").strip(),
        )


def esc(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def load_thresholds(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_jobs(csv_path: Path) -> List[Job]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [Job.from_row(r) for r in reader]


def classify_job(job: Job, now: datetime, t: Dict[str, Any]) -> Tuple[str, str]:
    """
    Status: OK / WARN / ALERT
    Rules:
      - Failed results => ALERT
      - Warning results => WARN (or ALERT if fail_on_warning_result true)
      - Stale based on last_success days => WARN/ALERT
    """
    allowed_success = set(
        v.lower() for v in t.get("allowed_success_values", ["success"])
    )
    allowed_warn = set(v.lower() for v in t.get("allowed_warning_values", ["warning"]))
    allowed_fail = set(
        v.lower() for v in t.get("allowed_fail_values", ["failed", "error"])
    )

    res = (job.last_result or "").lower()

    if res in allowed_fail:
        return "ALERT", f"Last result is {job.last_result}"
    if res in allowed_warn:
        if t.get("fail_on_warning_result", False):
            return "ALERT", f"Last result is {job.last_result}"
        # keep evaluating staleness too, but base status is WARN at least
        base = ("WARN", f"Last result is {job.last_result}")
    else:
        base = ("OK", "Last result OK")

    warn_days = float(t.get("warning_days", 2))
    stale_days = float(t.get("stale_days", 3))

    d = days_since(job.last_success, now)
    if d is None:
        # no last_success is suspicious: treat as ALERT
        return "ALERT", "No last_success timestamp"

    if d >= stale_days:
        return "ALERT", f"Stale: last success {d:.1f} days ago"
    if d >= warn_days:
        # if already WARN, keep WARN; if OK, warn
        if base[0] == "OK":
            return "WARN", f"Approaching stale: last success {d:.1f} days ago"
        return "WARN", f"{base[1]}; also last success {d:.1f} days ago"

    return base


def make_table(headers: List[str], rows: List[List[Any]]) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    if not rows:
        body = f"<tr><td colspan='{len(headers)}'><i>No data</i></td></tr>"
    else:
        body = "".join(
            "<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows
        )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def badge(status: str) -> str:
    cls = {"OK": "ok", "WARN": "warn", "ALERT": "bad"}.get(status, "ok")
    return f"<span class='badge {cls}'>{esc(status)}</span>"


def build_html(
    now: datetime, jobs: List[Job], t: Dict[str, Any], results: List[Dict[str, Any]]
) -> str:
    total = len(results)
    alerts = sum(1 for r in results if r["status"] == "ALERT")
    warns = sum(1 for r in results if r["status"] == "WARN")
    oks = sum(1 for r in results if r["status"] == "OK")

    summary = make_table(
        ["Total Jobs", "OK", "Warnings", "Alerts", "Stale Threshold"],
        [
            [
                str(total),
                str(oks),
                str(warns),
                str(alerts),
                f"{t.get('stale_days', 3)} days",
            ]
        ],
    )

    # Sections
    alert_rows = []
    warn_rows = []
    all_rows = []

    for r in results:
        all_rows.append(
            [
                badge(r["status"]),
                r["job_name"],
                r["last_result"],
                r["last_run"],
                r["last_success"],
                r["days_since_success"],
                r["duration_minutes"],
                r["reason"],
            ]
        )
        if r["status"] == "ALERT":
            alert_rows.append(
                [
                    r["job_name"],
                    r["last_result"],
                    r["last_success"],
                    r["days_since_success"],
                    r["reason"],
                ]
            )
        elif r["status"] == "WARN":
            warn_rows.append(
                [
                    r["job_name"],
                    r["last_result"],
                    r["last_success"],
                    r["days_since_success"],
                    r["reason"],
                ]
            )

    alerts_tbl = make_table(
        ["Job", "Last Result", "Last Success", "Days Since Success", "Reason"],
        alert_rows,
    )
    warns_tbl = make_table(
        ["Job", "Last Result", "Last Success", "Days Since Success", "Reason"],
        warn_rows,
    )
    all_tbl = make_table(
        [
            "Status",
            "Job",
            "Last Result",
            "Last Run",
            "Last Success",
            "Days Since Success",
            "Duration (min)",
            "Notes",
        ],
        all_rows,
    )

    generated = now.strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Backup Verification Report</title>
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
  <h1>Backup Verification Report</h1>
  <div class="meta">
    <div><b>Generated:</b> {esc(generated)}</div>
    <div><b>Stale threshold:</b> {esc(t.get("stale_days", 3))} days since last successful backup</div>
  </div>

  <h2>Summary</h2>
  {summary}

  <h2>Alerts</h2>
  {alerts_tbl}

  <h2>Warnings</h2>
  {warns_tbl}

  <h2>All Jobs</h2>
  {all_tbl}
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate backup verification report from a jobs CSV"
    )
    ap.add_argument(
        "--input",
        required=True,
        help="Path to jobs CSV (job_name,last_run,last_result,last_success,...)",
    )
    ap.add_argument("--thresholds", required=True, help="Path to thresholds.json")
    ap.add_argument("--outdir", required=True, help="Output folder")
    args = ap.parse_args()

    input_csv = Path(args.input)
    thresholds_path = Path(args.thresholds)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    t = load_thresholds(thresholds_path)
    jobs = load_jobs(input_csv)

    now = datetime.now()
    results: List[Dict[str, Any]] = []

    for job in jobs:
        status, reason = classify_job(job, now, t)
        d = days_since(job.last_success, now)
        results.append(
            {
                "job_name": job.job_name,
                "last_result": job.last_result,
                "last_run": job.last_run.isoformat(sep="T", timespec="seconds")
                if job.last_run
                else "",
                "last_success": job.last_success.isoformat(sep="T", timespec="seconds")
                if job.last_success
                else "",
                "days_since_success": f"{d:.2f}" if d is not None else "",
                "duration_minutes": f"{job.duration_minutes:.1f}"
                if job.duration_minutes is not None
                else "",
                "status": status,
                "reason": reason,
                "notes": job.notes,
            }
        )

    # Sort: ALERT first, then WARN, then OK; within that by days since success descending
    order = {"ALERT": 0, "WARN": 1, "OK": 2}

    def sort_key(r: Dict[str, Any]) -> Tuple[int, float]:
        d = 0.0
        try:
            d = float(r["days_since_success"]) if r["days_since_success"] else 0.0
        except Exception:
            d = 0.0
        return (order.get(r["status"], 9), -d)

    results.sort(key=sort_key)

    html_out = build_html(now, jobs, t, results)
    (outdir / "report.html").write_text(html_out, encoding="utf-8")
    (outdir / "report.json").write_text(
        json.dumps(
            {
                "generated_at": now.isoformat(timespec="seconds"),
                "thresholds": t,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote: {outdir / 'report.html'}")
    print(f"Wrote: {outdir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
