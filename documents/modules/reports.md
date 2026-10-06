# Module — Reports

Specification: §§6–7. Acceptance: AC-002. Offline transport details are in the sync module. This module owns the report record and the submit use case.

## Responsibility

Store a timestamped operational report: population, vulnerable-group counts, food, water, medicine, and optional incident notes. Keep the write path short. After commit, publish `report.submitted` when the report becomes the newest applied snapshot, or `report.stored_historical` when an older offline report must not overwrite newer information.

## Endpoints

### `POST /api/v1/reports/`

Permission: `report.submit`. Warden may submit only for the assigned shelter. The body includes `shelter_id` and the service rejects a mismatch with `404`.

Request `ReportCreate`:

| Field | Rule |
| --- | --- |
| `client_report_id` | UUID, required |
| `shelter_id` | UUID, required |
| `reported_at` | timestamp, required, not more than 5 minutes in the future |
| `population` | integer ≥ 0 |
| `vulnerability` | object with the five approved count keys, each ≥ 0, sum ≤ population |
| `resources` | array of exactly three items: `food`, `water`, `medicine`, each with `quantity` ≥ 0 and `unit` |
| `incident_notes` | optional, ≤ 2000 chars |
| `channel` | `web` for this endpoint |

Success, first write that applies: `201`, event `report.submitted`, `processing_status: "accepted"`.

Same `client_report_id` and identical payload: `200`, `meta.idempotent_replay: true`, event `report.duplicate_ignored` only the first time the duplicate is detected after the original; further replays do not append audit noise beyond a single duplicate marker. Implementation stores one duplicate-detected audit row per original id.

Same `client_report_id` and different payload: `409`, `DUPLICATE_MISMATCH`. Nothing is overwritten.

`reported_at` older than `shelter.last_applied_report_at`: `201`, report stored, `applied_to_current: false`, event `report.stored_historical`. Current population and stock stay as they were.

| Failure | Status | Code |
| --- | --- | --- |
| Bad schema | 400 | `VALIDATION_ERROR` |
| No permission | 403 | `PERMISSION_DENIED` |
| Shelter not visible | 404 | `NOT_FOUND` |

### `GET /api/v1/reports/{report_id}` and list routes

Permission: `report.read`, scope-filtered. Query on the collection: `shelter_id`, `from`, `to`, `channel`, pagination. Sort: `reported_at`.

`GET /api/v1/shelters/{shelter_id}/reports` is the shelter-scoped list.

## Workflow mapping

The warden’s online submit is the head of the section 7 workflow. This module stops at a durable report plus the primary event. Status, shortage, capacity, and officer-facing updates are subscribers.

## Channel

`channel = sms` or `telephony` is set only by the integrations module calling this service. The public web schema for `POST /reports/` accepts `web` only.

## Tests

AC-002: registered shelter, warden submits population and resources, row exists with `reported_at`. Validation failures for negative population, vulnerability sum above population, missing medicine, and future timestamp. Idempotent replay. Stale report does not change `last_applied_report_at`.
