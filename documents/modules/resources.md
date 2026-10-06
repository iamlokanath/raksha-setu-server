# Module — Resources

Specification: §§11–13. Shortage acceptance is AC-004 and is completed in the alerts module when a condition event is raised. This module owns quantities and the evaluation step.

## Responsibility

Track food, water, and medicine for each shelter: resource type, quantity, and unit. Compare the latest applied snapshot with approved configuration. Emit condition events. Do not invent thresholds.

## Read endpoints

### `GET /api/v1/shelters/{shelter_id}/resources`

Permission: `resource.read`. Returns the current snapshot for the three resource types. Missing snapshot returns quantities as `null` and `status: "unreported"` rather than zero, so “never reported” is distinct from “none left”.

### `GET /api/v1/resources/`

Permission: `resource.read`. Query: `block_id`, `resource_type`, `surplus` (`true` or `false`). `surplus=true` returns shelters whose latest applied quantity is above the approved surplus line. When OD-001 has no surplus line, the filter returns `422` and `CONFIGURATION_REQUIRED` instead of guessing a line. Unfiltered list still returns raw quantities.

There is no client `POST` that sets stock outside a report. Stock changes enter through `report.submitted`.

## Handler: snapshot

On `report.submitted`, upsert the three current rows and append history tied to `report_id`. Publish `resource.snapshot_updated`.

On `report.stored_historical`, append history only. Do not change the current row. Do not publish `resource.snapshot_updated`.

## Handler: shortage (OD-001)

Inputs that the specification requires the comparison to be able to use: available stock from the latest applied report. Consumption or a prediction formula may be added only as approved configuration.

When configuration for the tenant is absent:

- Publish `shortage.evaluation_skipped`.
- Do not open an alert.
- Leave shelter warning colour unchanged by shortage (status handler may still be `unknown`).

When configuration is present, compare using only that configuration. If the rule says a shortage is likely, publish `shortage.condition_met` with `shelter_id`, `resource_type`, `quantity`, `unit`, and `severity` taken from the configuration band (`attention` or `urgent`).

## Handler: capacity (OD-002)

Compare `population` from the applied report with shelter `capacity`.

Configuration absent: publish `capacity.evaluation_skipped`. Do not open a capacity alert.

Configuration present and the occupancy rule matches: publish `capacity.condition_met` with `population`, `capacity`, and `severity`.

## Surplus for redistribution

A shelter is a candidate source only when configuration defines a surplus line and the latest applied quantity is above it. The actions module listens for shortage events and reads this query. This module does not approve movement.

## Tests

- Report updates food, water, and medicine snapshots.
- Historical report does not replace the snapshot.
- No configuration → skip events and zero alerts.
- Approved fixture configuration → `shortage.condition_met` (AC-004 setup).
- `unreported` is not stored as zero.
