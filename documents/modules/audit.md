# Module — Audit

Specification: §21, AC-010. The UI history screen reads this list.

## Responsibility

Expose the append-only audit history produced by the event handler in document 05. This module does not write audit rows from controllers. Writes happen only in the audit subscriber.

## Endpoint

### `GET /api/v1/audit/`

Class-based `AuditListView`. Permission: `audit.read` (District Officer). Tenant scoped.

Query: `from`, `to`, `event_type`, `aggregate_id`, `page`, `page_size`.

Each item: `occurred_at`, `event_type`, `actor_id`, `aggregate_type`, `aggregate_id`, `request_id`, and a payload limited to operational identifiers and enums. The serializer drops any key named `password`, `password_hash`, `access_token`, `refresh_token`, or `token`.

| Outcome | Status | Code |
| --- | --- | --- |
| In scope | 200 | — |
| Bad query | 400 | `VALIDATION_ERROR` |
| Missing permission | 403 | `PERMISSION_DENIED` |

`GET` publishes no domain event.

There is no delete or patch.

## AC-010

A report submit, an alert acknowledgement, and an action decision each leave a row that this endpoint returns for the same tenant.

## Tests

- District officer receives those three event types.
- Block officer receives `403`.
- Tenant B cannot read tenant A’s `request_id`.
- A payload that accidentally included `password` is returned without that key.
