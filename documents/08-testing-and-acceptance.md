# 08 — Testing and Acceptance

Tests are written in the same change as behaviour. Each module’s `tests/` package covers that module. Cross-module workflows live in `tests/acceptance/`.

## Backend coverage required

- Models, schemas, services, repositories
- Authentication and authorization
- Tenant isolation
- API endpoints through the class-based views
- Business rules and event handlers
- Error envelope and status codes
- Database constraints
- Integration ports with fake adapters

## API cases required for each protected endpoint

- Success
- Invalid body or query
- Missing required field
- No token
- Wrong role
- Wrong tenant
- Not found
- Business-rule failure where the module defines one
- Duplicate and idempotency where the module defines them

Pagination and filters: dashboard, shelters, reports, alerts, actions.

Concurrency: two requests with the same `client_report_id` result in one applied report.

## Security cases

- Unauthenticated call to a shelter route returns `401`.
- Tenant B id on a tenant A token returns `404`.
- Warden cannot approve an action (`403`).
- Login response has no password hash.
- Alert list does not include resident-level personal data.
- Tampered access token returns `401`.
- Extra JSON field returns `400`.

## Event cases

- A successful report insert writes an outbox row for `report.submitted` in the same transaction (rollback test: failed request leaves no outbox row).
- Handler retry with the same `event_id` does not open two alerts.
- No `GET` writes an outbox domain event.

## Acceptance map

| ID | Proof |
| --- | --- |
| AC-001 | Shelter create stores every master field |
| AC-002 | Report stores timestamp, population, vulnerability, stock |
| AC-003 | Batch sync applies when processed; local queue is the client’s, server retains and dedupes |
| AC-004 | Fixture threshold → shortage alert |
| AC-005 | Four factors present; fixture weights each move the score |
| AC-006 | Surplus shelter appears as proposed source |
| AC-007 | Decision endpoint required; no autonomous execution |
| AC-008 | All lifecycle states persisted in order |
| AC-009 | Summary and list expose urgent, attention, surplus, unresolved |
| AC-010 | Audit rows for report, alert transition, and action decision |

AC-010 is failed if any of those actions can complete with an empty audit table.

## Definition of done (server)

- Behaviour is in this document set.
- Open decisions are read from configuration, not guessed.
- Endpoint is class-based, versioned, and in OpenAPI.
- Schemas and the standard error body are used.
- Permission and tenant checks exist.
- State change publishes the specified event.
- Tests for the acceptance row above pass.
- No file exceeds 500 lines.
- No secret in source.

## Pilot outputs this service must be able to support

| Window | Output |
| --- | --- |
| Weeks 1–2 | Tenant, blocks, shelters, users |
| Weeks 3–5 | Reporting and sync |
| Weeks 6–7 | Dashboard, alerts, surplus and proposed actions |
| Week 12 | Records required for the go / no-go review, including audit history |
