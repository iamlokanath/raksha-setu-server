# 04 — Schemas, Validation, Status Codes, and Errors

## Schema rules

- Request, query, and response bodies are named schema types (Pydantic models colocated with the module).
- OpenAPI is generated from those types.
- Extra JSON fields are rejected.
- Identifiers are UUID strings.
- Timestamps are ISO-8601 in UTC.
- Quantities are non-negative decimals with an explicit unit.
- Counts of people are non-negative integers.
- Enumerations used by clients are closed: shelter status, alert type, alert severity, alert status, action decision, resource type, and role.
- Text fields that officers read have a maximum length declared on the schema.
- Schemas do not include fields the role must not see. Where a field is restricted, the response schema for that permission omits it.

## Two validation stages

1. **Structural validation** in the view, before the service. Type, required field, format, range, enum, and unknown-field failures return `400` and `VALIDATION_ERROR`.
2. **Domain validation** in the service. Illegal transitions, missing approval, and scope failures return the status code named in the module. They use a domain error code, not a generic validation code.

Controllers do not re-implement domain checks that the service already owns.

## Shared success bodies

Single resource:

```json
{
  "data": {},
  "meta": {
    "request_id": "3f1c1d4e-6b2a-4e8a-9c1d-0a1b2c3d4e5f",
    "timestamp": "2026-10-05T12:00:00Z"
  }
}
```

Collection:

```json
{
  "data": [],
  "meta": {
    "request_id": "3f1c1d4e-6b2a-4e8a-9c1d-0a1b2c3d4e5f",
    "timestamp": "2026-10-05T12:00:00Z",
    "page": 1,
    "page_size": 20,
    "total": 0
  }
}
```

Idempotent replay adds `meta.idempotent_replay: true` and returns the stored resource with `200`.

Async accept (sync batch queued):

```json
{
  "data": {
    "batch_id": "uuid",
    "accepted_count": 2
  },
  "meta": {
    "request_id": "uuid",
    "timestamp": "2026-10-05T12:00:00Z"
  }
}
```

`204` responses have an empty body.

## Error body

Every error uses the same envelope. User-facing copy is not authored here. The UI maps `code` and `details[].code` through the localization layer.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "details": [
      {
        "field": "population",
        "code": "MIN_VALUE"
      }
    ],
    "request_id": "3f1c1d4e-6b2a-4e8a-9c1d-0a1b2c3d4e5f"
  }
}
```

`details` is an empty array when the error is not field-specific.

## Status codes

| HTTP | When | `error.code` |
| --- | --- | --- |
| 200 | Read, update, legal transition, idempotent replay | — |
| 201 | First successful create | — |
| 202 | Command durably queued; processing continues by events | — |
| 204 | Logout | — |
| 400 | Malformed JSON, schema validation failure | `VALIDATION_ERROR` |
| 401 | Missing or invalid authentication | `AUTH_INVALID` |
| 403 | Authenticated but not permitted for this action | `PERMISSION_DENIED` |
| 404 | Resource not in the caller’s visible scope, including other tenants | `NOT_FOUND` |
| 409 | Duplicate id with different payload, or stale write that would overwrite newer state | `DUPLICATE_MISMATCH` or `CONFLICT_STALE` |
| 422 | Well-formed request that breaks a business rule or alert/action transition | domain code below |
| 500 | Unhandled failure. No stack trace in the body. | `INTERNAL_ERROR` |

Domain codes for `422`:

| Code | Meaning |
| --- | --- |
| `INVALID_STATE` | Transition is not in the allowed lifecycle |
| `HUMAN_APPROVAL_REQUIRED` | A client attempted to execute relief without an officer decision |
| `CONFIGURATION_REQUIRED` | A calculation was requested that still depends on OD-001, OD-002, or OD-003 |
| `SCOPE_VIOLATION` | Actor’s assignment does not cover the shelter (use `404` when existence must stay hidden; this code is for an explicit mismatch the module documents) |

Do not invent additional HTTP codes per endpoint. Map every failure onto this table in the module spec.

## Field constraints used across modules

| Field | Constraint |
| --- | --- |
| `population` | integer, ≥ 0 |
| vulnerability counts | integer, ≥ 0; sum may not exceed `population` |
| `quantity` | decimal, ≥ 0 |
| `unit` | required when quantity is sent; closed list per resource type once configured, otherwise a non-empty string up to 32 characters |
| `incident_notes` | optional string, max 2000 characters |
| `reported_at` | required timestamp; may be in the past for offline capture; may not be more than 5 minutes in the future |
| `client_report_id` | required UUID on report create and sync |

Vulnerability groups in the first release are counts only. The approved group keys are: `children`, `older_adults`, `pregnant_women`, `persons_with_disability`, `injured_or_sick`. Adding a group is a specification change. The API stores counts for these keys and does not store names of individuals.

## Error handling inside the server

- Schema errors are raised by the base view and rendered by one exception handler.
- Services raise typed domain errors. They do not raise bare `Exception` for expected rule failures.
- The exception handler logs `request_id` and the error code. It does not log the request body.
- `500` is the only response for unexpected exceptions. Callers still receive the standard envelope.
