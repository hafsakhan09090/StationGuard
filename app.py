"""
StationGuard - Station Health Early Warning System
Fynd Hiring Hackathon 2026

Monitors per-station scan rate, heartbeat interval and error rate against a
rolling baseline, and classifies each station as HEALTHY, SLOW, DEGRADING or
SILENT. Alerts include the specific metrics that triggered them so a field
engineer can act on them immediately, not just see a label.
"""

import os
import time
import sqlite3
from fastapi import FastAPI
from pydantic import BaseModel

DB = os.environ.get("STATIONGUARD_DB", "stationguard.db")

app = FastAPI(title="StationGuard - Station Health Early Warning System")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id TEXT NOT NULL,
            event_type TEXT NOT NULL,  -- heartbeat | scan | error
            value REAL DEFAULT 1,
            ts REAL NOT NULL
        )"""
    )
    conn.commit()
    conn.close()


init_db()


class EventIn(BaseModel):
    value: float = 1.0


def now():
    return time.time()


@app.post("/stations/{station_id}/heartbeat")
def heartbeat(station_id: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO events (station_id, event_type, value, ts) VALUES (?, 'heartbeat', 1, ?)",
        (station_id, now()),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/stations/{station_id}/scan")
def scan(station_id: str, event: EventIn = EventIn()):
    conn = get_db()
    conn.execute(
        "INSERT INTO events (station_id, event_type, value, ts) VALUES (?, 'scan', ?, ?)",
        (station_id, event.value, now()),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/stations/{station_id}/error")
def error(station_id: str, event: EventIn = EventIn()):
    conn = get_db()
    conn.execute(
        "INSERT INTO events (station_id, event_type, value, ts) VALUES (?, 'error', ?, ?)",
        (station_id, event.value, now()),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


def _rate_per_minute(rows, window_seconds):
    if not rows or window_seconds <= 0:
        return 0.0
    total = sum(r["value"] for r in rows)
    return total / (window_seconds / 60)


def compute_health(station_id: str):
    conn = get_db()
    t = now()

    # Recent window: last 5 minutes
    recent_scans = conn.execute(
        "SELECT value FROM events WHERE station_id=? AND event_type='scan' AND ts >= ?",
        (station_id, t - 300),
    ).fetchall()
    recent_errors = conn.execute(
        "SELECT value FROM events WHERE station_id=? AND event_type='error' AND ts >= ?",
        (station_id, t - 300),
    ).fetchall()
    last_heartbeat = conn.execute(
        "SELECT MAX(ts) as ts FROM events WHERE station_id=? AND event_type='heartbeat'",
        (station_id,),
    ).fetchone()

    # Baseline window: 5 to 35 minutes ago (30-minute rolling baseline)
    baseline_scans = conn.execute(
        "SELECT value FROM events WHERE station_id=? AND event_type='scan' AND ts BETWEEN ? AND ?",
        (station_id, t - 2100, t - 300),
    ).fetchall()
    conn.close()

    recent_rate = _rate_per_minute(recent_scans, 300)
    baseline_rate = _rate_per_minute(baseline_scans, 1800) if baseline_scans else (recent_rate or 1.0)

    scan_count = sum(r["value"] for r in recent_scans)
    error_count = sum(r["value"] for r in recent_errors)
    error_rate = (error_count / scan_count * 100) if scan_count else 0.0

    heartbeat_age = (t - last_heartbeat["ts"]) if last_heartbeat and last_heartbeat["ts"] else None
    deviation = ((baseline_rate - recent_rate) / baseline_rate * 100) if baseline_rate else 0.0

    status = "HEALTHY"
    reasons = []

    if heartbeat_age is None or heartbeat_age > 120:
        status = "SILENT"
        reasons.append(
            "No heartbeat ever received" if heartbeat_age is None
            else f"No heartbeat received in {heartbeat_age:.0f}s (over the 2-minute threshold)"
        )
    else:
        if heartbeat_age > 60 or deviation > 50 or error_rate > 15:
            status = "DEGRADING"
        elif heartbeat_age > 30 or deviation > 25 or error_rate > 5:
            status = "SLOW"

        if deviation > 25:
            reasons.append(f"Scan rate dropped {deviation:.0f}% below the 30-minute baseline")
        if error_rate > 5:
            reasons.append(f"Error rate at {error_rate:.1f}% (baseline threshold 5%)")
        if heartbeat_age > 30:
            reasons.append(f"Last heartbeat {heartbeat_age:.0f}s ago")
        if not reasons:
            reasons.append("All metrics within normal range")

    return {
        "station_id": station_id,
        "status": status,
        "recent_scan_rate_per_min": round(recent_rate, 2),
        "baseline_scan_rate_per_min": round(baseline_rate, 2),
        "deviation_pct": round(deviation, 1),
        "error_rate_pct": round(error_rate, 1),
        "heartbeat_age_seconds": round(heartbeat_age, 1) if heartbeat_age is not None else None,
        "reasons": reasons,
    }


@app.get("/stations/{station_id}/health")
def get_health(station_id: str):
    return compute_health(station_id)


@app.get("/stations")
def list_stations():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT station_id FROM events").fetchall()
    conn.close()
    return [compute_health(r["station_id"]) for r in rows]


@app.get("/alerts")
def alerts():
    return [s for s in list_stations() if s["status"] in ("SLOW", "DEGRADING", "SILENT")]


@app.get("/")
def root():
    return {
        "service": "StationGuard",
        "endpoints": [
            "POST /stations/{station_id}/heartbeat",
            "POST /stations/{station_id}/scan {value}",
            "POST /stations/{station_id}/error {value}",
            "GET /stations/{station_id}/health",
            "GET /stations",
            "GET /alerts",
        ],
    }
