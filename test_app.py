import os

os.environ["STATIONGUARD_DB"] = "test_stationguard.db"
if os.path.exists("test_stationguard.db"):
    os.remove("test_stationguard.db")

import app as appmodule  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(appmodule.app)


def test_root_lists_endpoints():
    r = client.get("/")
    assert r.status_code == 200
    assert "endpoints" in r.json()


def test_station_with_no_data_is_silent():
    r = client.get("/stations/UNKNOWN_STATION/health")
    data = r.json()
    assert data["status"] == "SILENT"
    assert data["heartbeat_age_seconds"] is None


def test_heartbeat_and_scans_make_station_healthy():
    client.post("/stations/S1/heartbeat")
    client.post("/stations/S1/scan", json={"value": 5})
    r = client.get("/stations/S1/health")
    data = r.json()
    assert data["station_id"] == "S1"
    assert data["status"] in ("HEALTHY", "SLOW")
    assert data["heartbeat_age_seconds"] is not None


def test_error_rate_is_computed_from_scans_and_errors():
    for _ in range(10):
        client.post("/stations/S2/scan", json={"value": 1})
    client.post("/stations/S2/heartbeat")
    for _ in range(3):
        client.post("/stations/S2/error", json={"value": 1})
    r = client.get("/stations/S2/health")
    data = r.json()
    assert data["error_rate_pct"] > 0
    assert data["status"] in ("SLOW", "DEGRADING", "HEALTHY")


def test_alerts_only_includes_unhealthy_stations():
    client.post("/stations/S3/heartbeat")
    client.post("/stations/S3/scan", json={"value": 100})
    r = client.get("/alerts")
    statuses = {a["status"] for a in r.json()}
    assert "HEALTHY" not in statuses


def test_list_stations_returns_all_seen_stations():
    r = client.get("/stations")
    ids = {s["station_id"] for s in r.json()}
    assert "S1" in ids
    assert "UNKNOWN_STATION" in ids
