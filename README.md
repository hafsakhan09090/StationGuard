# StationGuard — Station Health Early Warning System

Fynd Hiring Hackathon 2026 submission.

## Solution overview
A station going quiet today is only noticed when the production line stops.
StationGuard monitors three signals per station — heartbeat interval, scan
rate and error rate — against a rolling 30-minute baseline, and classifies
each station as `HEALTHY`, `SLOW`, `DEGRADING`, or `SILENT`. Alerts are
explainable: instead of returning a bare status, the API returns *why*
("scan rate dropped 38% below the 30-minute baseline"), so a field engineer
can act immediately instead of digging through raw logs.

## Technology stack
- Python 3
- FastAPI (REST API)
- SQLite (event storage, no external DB needed)
- pytest + FastAPI TestClient (automated tests)

## Setup instructions
```bash
pip install -r requirements.txt
```

## Execution instructions
```bash
uvicorn app:app --reload
```
The API is then live at `http://127.0.0.1:8000`. Interactive docs at
`http://127.0.0.1:8000/docs`.

### Example usage
```bash
curl -X POST http://127.0.0.1:8000/stations/A1/heartbeat
curl -X POST http://127.0.0.1:8000/stations/A1/scan -H "Content-Type: application/json" -d '{"value": 5}'
curl -X POST http://127.0.0.1:8000/stations/A1/error -H "Content-Type: application/json" -d '{"value": 1}'
curl http://127.0.0.1:8000/stations/A1/health
curl http://127.0.0.1:8000/alerts
```

## Running tests
```bash
pytest -v
```

## Database schema
Single `events` table (created automatically on first run):

| column      | type    | notes                              |
|-------------|---------|-------------------------------------|
| id          | INTEGER | primary key, autoincrement         |
| station_id  | TEXT    | station identifier                 |
| event_type  | TEXT    | `heartbeat` \| `scan` \| `error`    |
| value       | REAL    | count for scan/error events        |
| ts          | REAL    | unix timestamp                     |

Storing raw events rather than pre-aggregated counters means the baseline
window can be recomputed or tuned later without losing history.

## API endpoints
- `POST /stations/{station_id}/heartbeat` — record a heartbeat
- `POST /stations/{station_id}/scan` `{"value": n}` — record scan activity
- `POST /stations/{station_id}/error` `{"value": n}` — record an error
- `GET /stations/{station_id}/health` — health classification + reasons
- `GET /stations` — health of every station seen so far
- `GET /alerts` — only stations that are SLOW, DEGRADING or SILENT

## Assumptions and design decisions
- **Recent window**: last 5 minutes. **Baseline window**: the preceding 30
  minutes (5–35 minutes ago), so the baseline isn't contaminated by the
  current incident.
- **Silent** takes priority over every other signal: no heartbeat in over
  2 minutes means the station is assumed offline regardless of historical
  scan rate.
- Thresholds (30s / 60s / 120s heartbeat age, 25% / 50% scan-rate
  deviation, 5% / 15% error rate) are simple fixed cutoffs chosen to be
  easy to justify and tune; a production version would likely learn
  per-station baselines instead of using one global threshold set.
- SQLite is used for simplicity and zero setup; the schema would map
  directly onto Postgres for a production deployment.
- No authentication was added since the challenge scope is the monitoring
  logic itself, not access control.

## AI tool usage declaration
Claude (Anthropic) was used to help scaffold the FastAPI project structure,
the SQLite schema, and the initial classification thresholds, and to draft
this README. The rolling-baseline logic, threshold values and test cases
were reviewed, run, and verified by the author, who can explain and modify
any part of the code during a live walkthrough.
