# Module — Alerts

Specification: §14. Acceptance: AC-004, AC-008.

## Responsibility

Represent shortage and capacity warnings. Track each alert through the approved lifecycle. Support severity, grouping, and automatic downgrade or clear when a later evaluation says the condition eased. Threshold calibration is configuration (OD-001, OD-002), aimed at reducing alert fatigue. This module does not choose the numeric thresholds.

## Lifecycle

Allowed forward transitions:

```
detected → acknowledged → action_planned → action_in_progress → resolved → closed
```

Illegal jumps return `422` and `INVALID_STATE`. The row stays unchanged.

System transitions, configuration-driven:

- `alert.downgraded` may lower severity from `urgent` to `attention` while status is before `resolved`.
- `alert.auto_cleared` may move an alert that is not yet `action_in_progress` to `resolved` when the condition is gone, then an officer `close` is still required to reach `closed`. Auto-clear must not skip the audit trail.

No client route creates an alert directly. Creation is the handler for `shortage.condition_met` and `capacity.condition_met`.

## Grouping

An open alert already exists for the same tenant, shelter, type, and resource type (resource type null for capacity): update severity if the new condition is higher, and do not insert a second open row. Publish `alert.detected` only for the first open row. Subsequent escalations publish `alert.detected` with `grouped: true` and the same `alert_id` so dashboards can refresh without duplicate cards.

## Endpoints

All transitions are class-based `POST` views. Body schema `AlertTransition`: optional `note` ≤ 1000 characters.

| Route | Permission | From → to | Event |
| --- | --- | --- | --- |
| `/acknowledge` | `alert.acknowledge` | detected → acknowledged | `alert.acknowledged` |
| `/plan` | `alert.plan` | acknowledged → action_planned | `alert.action_planned` |
| `/start` | `alert.progress` | action_planned → action_in_progress | `alert.action_in_progress` |
| `/resolve` | `alert.resolve` | action_in_progress → resolved | `alert.resolved` |
| `/close` | `alert.close` | resolved → closed | `alert.closed` |

Success: `200` and `AlertResponse` (`id`, `shelter_id`, `type`, `severity`, `status`, `created_at`, `resource_type`).

| Failure | Status | Code |
| --- | --- | --- |
| Wrong current status | 422 | `INVALID_STATE` |
| Not permitted | 403 | `PERMISSION_DENIED` |
| Outside scope | 404 | `NOT_FOUND` |

### `GET /api/v1/alerts/` and `GET /api/v1/alerts/{alert_id}`

Permission: `alert.read`. Query: `status`, `severity`, `type`, `block_id`, `shelter_id`, pagination. Sort: `created_at`, `severity`.

## AC-004

Given an approved shortage configuration and a report that meets it, the evaluation emits `shortage.condition_met` and this module stores an alert with type `shortage`, a severity, shelter, created time, and status `detected`.

## AC-008

A test walks one alert across every status in order and asserts the audit events. A second test asserts each illegal jump is rejected.

## Tests

Also cover grouping, downgrade, auto-clear stopping before `closed`, and warden inability to close.
