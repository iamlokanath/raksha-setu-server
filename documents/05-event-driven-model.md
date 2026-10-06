# 05 — Event-Driven Model

## Rule

Every successful state-changing API publishes exactly one primary domain event after the database commit. Further facts (status recalculation, shortage check, capacity check, alert open, recommendation) are produced by handlers, which may publish their own events.

`GET` requests do not publish domain events.

The HTTP response does not wait for downstream handlers except where the module says the primary write includes the immediate result (for example, the report row itself). Shelter status and alerts may update a moment later. Clients refresh from the read models. The report response includes `processing_status: "accepted"` so the UI can show that follow-on checks are in progress.

`POST /api/v1/sync/reports` returns `202` after the batch and its items are durable. Item application is event-driven.

## Envelope

```json
{
  "event_id": "uuid",
  "event_type": "report.submitted",
  "occurred_at": "2026-10-05T12:00:00Z",
  "tenant_id": "uuid",
  "actor_id": "uuid",
  "request_id": "uuid",
  "aggregate_type": "shelter_report",
  "aggregate_id": "uuid",
  "payload": {}
}
```

`actor_id` is null only for events emitted by the system, and the payload then includes `cause_event_id`.

## Delivery

1. The service writes domain rows and an outbox row in the same transaction.
2. Commit.
3. A dispatcher reads the outbox and invokes in-process handlers.
4. Handlers are idempotent on `event_id`.
5. A handler failure leaves the outbox row retryable. It does not roll back the already committed user command.
6. Poison messages after repeated failure are recorded for operator review and do not block unrelated events.

The dispatcher is an internal port. Replacing in-process delivery with a broker later must not change event names or payloads.

## Catalogue

| Event | Publisher | Subscribers |
| --- | --- | --- |
| `auth.login_succeeded` | auth | audit |
| `auth.login_failed` | auth | audit |
| `auth.logout` | auth | audit |
| `user.registered` | users | audit |
| `user.assignment_changed` | users | audit |
| `shelter.registered` | shelters | audit |
| `shelter.updated` | shelters | audit, dashboard read model |
| `report.submitted` | reports | resources, shelter status, audit |
| `report.stored_historical` | sync / reports | audit |
| `report.duplicate_ignored` | reports | audit |
| `sync.batch_accepted` | sync | report apply handler |
| `resource.snapshot_updated` | resources | shortage handler, capacity handler, dashboard |
| `shelter.status_recalculated` | shelter status handler | dashboard, audit |
| `shortage.evaluation_skipped` | shortage handler | audit (configuration missing, OD-001) |
| `shortage.condition_met` | shortage handler | alerts |
| `capacity.evaluation_skipped` | capacity handler | audit (OD-002) |
| `capacity.condition_met` | capacity handler | alerts |
| `alert.detected` | alerts | dashboard, audit |
| `alert.acknowledged` | alerts | dashboard, audit |
| `alert.action_planned` | alerts | dashboard, audit |
| `alert.action_in_progress` | alerts | dashboard, audit |
| `alert.resolved` | alerts | dashboard, audit |
| `alert.closed` | alerts | dashboard, audit |
| `alert.downgraded` | alerts | dashboard, audit |
| `alert.auto_cleared` | alerts | dashboard, audit |
| `action.proposed` | actions | dashboard, audit |
| `action.approved` | actions | audit, receiving shelter visibility |
| `action.modified` | actions | audit |
| `action.rejected` | actions | audit |
| `action.receipt_confirmed` | actions | resources, alerts, audit |

Payloads are defined in the module that publishes the event. Handlers must tolerate an unknown future field and must reject a missing required field by failing the handler, not by guessing.

## Status and warning chain

This is the specification workflow in section 7, expressed as events:

```
report.submitted
  → resource.snapshot_updated
  → shelter.status_recalculated
  → shortage.condition_met or shortage.evaluation_skipped
  → capacity.condition_met or capacity.evaluation_skipped
  → alert.detected (only when a condition event fired)
  → action.proposed (only when a shortage alert has a candidate surplus shelter)
```

Automatic clearing: when a later snapshot no longer meets an approved threshold, the alert handler may publish `alert.downgraded` or `alert.auto_cleared`. Clearing is a configured behaviour and must be tested. It must never delete the alert row.

## Audit

The audit handler appends an immutable history row for every event in the catalogue except `shortage.evaluation_skipped` and `capacity.evaluation_skipped`, which are still stored but marked as technical skips. Audit storage is append-only.

## What events must not do

- Dispatch stock or medicine.
- Change an action from `proposed` to `approved`.
- Drop an older report on the floor. Older reports are stored as history and marked not applied to the current snapshot.
