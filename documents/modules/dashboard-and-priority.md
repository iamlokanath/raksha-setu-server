# Module — Dashboard and Priority

Specification: §§17–19. Acceptance: AC-005, AC-009.

## Responsibility

Serve the shared operational view. Answer, for an authorized officer:

- Which shelters need immediate help?
- Which shelters are approaching a problem?
- Where is available surplus?
- Which actions remain unresolved?

Reads are queries over current snapshots, alerts, and actions. They do not change state and do not emit domain events.

## Priority (OD-003)

The score, when configuration exists, is a pure function of four inputs. All four must contribute. None may be dropped:

| Factor | Source |
| --- | --- |
| Shortage urgency | Highest open shortage severity for the shelter; none is the zero contribution |
| Vulnerable population | Sum of the five approved counts on the latest applied report |
| Occupancy pressure | `population / capacity` when capacity > 0 |
| Issue age | Time since the oldest open alert `created_at`, or since `reported_at` when the view is about an unalerted report |

Until weights are approved, `GET` responses include `priority_factors` and set `priority_score` to `null`. They must not substitute an equal-weight formula. When weights exist in tenant configuration, `priority_score` is a number and `priority_factors` still returns so the officer can see why. The score is explainable input to judgment, not an order.

AC-005 is satisfied when a test with approved fixture weights shows each factor changing the score in the configured direction, and a test without configuration shows a null score plus all four factors.

## Endpoints

### `GET /api/v1/dashboard/summary`

Permission: `dashboard.read`.

Response `DashboardSummary`:

| Field | Meaning |
| --- | --- |
| `urgent_shelter_count` | `current_status = red` |
| `attention_shelter_count` | `current_status = yellow` |
| `unknown_shelter_count` | no applied report, or status not calculable |
| `surplus_shelter_count` | shelters with at least one resource above the surplus line; `null` if OD-001 unset |
| `unresolved_action_count` | decisions `proposed` plus approved/modified without receipt |
| `open_alert_count` | status not in `resolved`, `closed` |

Block officers receive counts for their block only. The service applies that filter. A block officer who passes another `block_id` receives `403`.

### `GET /api/v1/dashboard/shelters`

Permission: `dashboard.read`.

Query schema (section 19 filters):

| Parameter | Rule |
| --- | --- |
| `status` | `green`, `yellow`, `red`, `unknown` |
| `block_id` | UUID in tenant; forced for block officers |
| `shortage_type` | `food`, `water`, `medicine` |
| `occupancy` | `below_attention`, `attention`, `urgent`, `unknown` |
| `priority` | `high`, `medium`, `low`, `unscored` |

`priority=high|medium|low` requires OD-003 bands. If weights are absent, those three values return `422` `CONFIGURATION_REQUIRED`. `priority=unscored` remains valid.

Each item includes shelter name, location label, block, capacity, population, vulnerability counts, stock quantities, `current_status`, latest report time, open alerts, proposed actions, and `priority_factors` / `priority_score`.

Map coordinates are included only when the shelter master has them. The API does not geocode free text.

Sort: `priority_score` (nulls last), then `current_status` urgent first, then name. Pagination applies.

## Status colours

| Value | Section 10 meaning | Set when |
| --- | --- | --- |
| `red` | Urgent. Immediate action required. | Approved config maps the condition to urgent |
| `yellow` | Attention required. Approaching a concern threshold. | Approved config maps the condition to attention |
| `green` | Stable. | A report is applied and no approved rule says yellow or red |
| `unknown` | Not a section 10 status. Data is insufficient or config is absent. | No applied report, or OD-001/OD-002 missing so colour would be a guess |

The status handler listens to `resource.snapshot_updated` and writes `shelter.status_recalculated`.

## AC-009

An officer fixture can call summary and the shelter list and identify at least one urgent shelter, one attention shelter, one surplus shelter (under fixture config), and one unresolved proposed action.

## Tests

- Filter combinations return only matches.
- Block officer scope cannot be widened.
- Factors present for two shelters with different vulnerability and age.
- No weight config → null scores.
- Read endpoints publish no outbox rows.
