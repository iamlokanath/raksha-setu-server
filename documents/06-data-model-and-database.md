# 06 — Data Model and Database

## Engine

PostgreSQL. Schema changes ship as Alembic revisions in `migrations/`. Production schema is not edited by hand.

SQLAlchemy models in each module’s `models/` package are the mapping. Django models are not created for these tables.

## Tenancy column

Every tenant-owned table has `tenant_id` (UUID, not null) and an index that leads with `tenant_id`. Repositories add this predicate in one shared query helper. See document 07.

## Entities

### Tenant

District boundary. Fields: `id`, `name`, `code`, `status`.

### Block

Subdivision inside one tenant. Fields: `id`, `tenant_id`, `name`, `code`.

### User

Fields: `id`, `tenant_id`, `name`, `role`, `organization`, `status`, `password_hash` (null when SSO-only).

### Assignment

Fields: `id`, `tenant_id`, `user_id`, `shelter_id` nullable, `block_id` nullable, `support_functions` for volunteers.

A warden assignment has `shelter_id`. A block officer assignment has `block_id`. A district officer assignment has neither shelter nor block, and the tenant is the scope.

### Shelter

Fields required by section 5: `id`, `tenant_id`, `block_id`, `name`, `location_label`, `latitude` nullable, `longitude` nullable, `capacity`, `warden_user_id`, `reporting_contact`, `operational_status` (`active` or `inactive` as master status, distinct from Green/Yellow/Red).

Current derived snapshot (updated by events, not by the warden directly): `current_status` (`green`, `yellow`, `red`, or `unknown`), `last_applied_report_at`, `current_population`.

`unknown` means no applied report yet, or warning configuration is not approved. It is not a fourth business status from section 10. Section 10 statuses are only green, yellow, and red, and they are set only when the relevant configuration exists.

### Shelter report

Fields: `id` (server id), `client_report_id`, `tenant_id`, `shelter_id`, `reported_at`, `received_at`, `population`, vulnerability counts, `incident_notes`, `channel` (`web`, `sms`, `telephony`), `applied_to_current` (boolean), `actor_id`.

Unique constraint: (`tenant_id`, `client_report_id`).

### Resource snapshot

One current row per shelter and resource type, plus history.

Resource types in the first release: `food`, `water`, `medicine`.

Fields: `id`, `tenant_id`, `shelter_id`, `report_id`, `resource_type`, `quantity`, `unit`, `recorded_at`.

### Alert

Fields: `id`, `tenant_id`, `shelter_id`, `type` (`shortage`, `capacity`), `resource_type` nullable, `severity` (`attention`, `urgent`), `status`, `created_at`, `updated_at`, `cause_event_id`.

`status` follows section 14: `detected`, `acknowledged`, `action_planned`, `action_in_progress`, `resolved`, `closed`.

### Action

Relief coordination record. Fields: `id`, `tenant_id`, `alert_id`, `source_shelter_id`, `destination_shelter_id`, `resource_type`, `suggested_quantity`, `decision` (`proposed`, `approved`, `modified`, `rejected`), `decided_by`, `decided_at`, `decision_note`, `status`, `receipt_confirmed_at`, `explanation`.

`explanation` states why the source was suggested (surplus on the latest applied report, same tenant). It is not an instruction to move stock.

### Audit event

Fields: `id`, `tenant_id`, `event_id`, `event_type`, `actor_id`, `aggregate_type`, `aggregate_id`, `occurred_at`, `payload` JSON. No updates and no deletes in application code.

### Outbox

Fields: `event_id`, `tenant_id`, `event_type`, `payload`, `created_at`, `published_at`, `attempts`, `last_error`.

### Idempotency / sync batch

Fields for a batch: `id`, `tenant_id`, `actor_id`, `created_at`. Items reference `client_report_id` and processing state (`queued`, `applied`, `stored_historical`, `duplicate`, `rejected`).

## History

Reports, alerts, decisions, actions, and resolutions are retained. Updating current shelter snapshot does not destroy prior reports. Closing an alert does not delete it.

## Indexing minimum

- Shelter by (`tenant_id`, `block_id`, `current_status`)
- Report by (`tenant_id`, `shelter_id`, `reported_at`)
- Alert by (`tenant_id`, `status`, `severity`)
- Action by (`tenant_id`, `decision`)
- Unique (`tenant_id`, `client_report_id`)

## Configuration tables

Tenant configuration holds approved JSON for OD-001, OD-002, and OD-003 when, and only when, officials approve it. Empty configuration is valid and means “do not emit the dependent alert or official score”.
