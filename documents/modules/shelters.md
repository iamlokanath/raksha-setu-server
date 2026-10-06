# Module — Shelters

Specification: §5. Acceptance: AC-001.

## Responsibility

Maintain the pre-registered shelter master. A shelter exists before seasonal reporting. This module stores identity and capacity. It does not compute Green/Yellow/Red; that snapshot is updated by the status handler.

## Endpoints

### `POST /api/v1/shelters/`

Permission: `shelter.register`.

Request `ShelterCreate`:

| Field | Rule |
| --- | --- |
| `name` | required, 1–200 chars |
| `block_id` | required, must belong to the caller’s tenant |
| `location_label` | required, 1–300 chars |
| `latitude`, `longitude` | optional pair; both or neither; valid ranges |
| `capacity` | required integer, ≥ 1 |
| `warden_user_id` | required, user in tenant with warden role |
| `reporting_contact` | required, 1–50 chars (phone or radio id; not a free personal dossier) |
| `operational_status` | `active` or `inactive`, default `active` |

Success: `201` and `ShelterResponse`. Event: `shelter.registered`.

| Failure | Status | Code |
| --- | --- | --- |
| Invalid body | 400 | `VALIDATION_ERROR` |
| Missing permission | 403 | `PERMISSION_DENIED` |
| Block or warden outside tenant | 404 | `NOT_FOUND` |

### `GET /api/v1/shelters/`

Permission: `shelter.read`. Scope filter is mandatory (own shelter, own block, or whole tenant). Query: `block_id`, `operational_status`, `page`, `page_size`, `sort` in `name`, `current_status`.

### `GET /api/v1/shelters/{shelter_id}`

Permission: `shelter.read` plus scope. `404` outside scope. Response includes master fields, `current_status`, `current_population`, and `last_applied_report_at`. It does not include another shelter’s reports.

### `PATCH /api/v1/shelters/{shelter_id}`

Permission: `shelter.update`. Partial master update. At least one field. Event: `shelter.updated`. Changing capacity emits the event; the capacity handler decides whether a warning is due, and only when OD-002 is configured.

## Rules

- Shelter ids are server-generated UUIDs.
- Deleting a shelter is not supported. Set `operational_status` to `inactive`. Historical reports remain.
- Adding a shelter is data, not a code change (non-functional requirement: add shelters without rebuilding).

## Tests

AC-001: an authorized administrator registers a shelter and all required master fields are stored. A warden receives `403` on create. A district user cannot read a shelter from another tenant.
