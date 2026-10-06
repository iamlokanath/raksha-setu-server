# Module — Actions (Redistribution and Human Approval)

Specification: §§15–16. Acceptance: AC-006, AC-007.

## Responsibility

Suggest a nearby shelter with reported surplus, record an officer decision, and record receipt confirmation. The system may detect, rank, recommend, and explain. It must not dispatch relief or redirect medicine by itself.

## Suggestion flow

```
shortage.condition_met
  → find shelters in the same tenant with surplus of that resource on the latest applied report
  → prefer the same block, then other blocks in the tenant
  → create Action decision = proposed
  → publish action.proposed
```

“Nearby” in this baseline means same district tenant, with same-block candidates ordered first. A geographic distance formula is not approved. Do not invent a kilometre cutoff. If coordinates exist they may be returned as facts for the officer. They must not silently drop a same-district surplus shelter.

If OD-001 has no surplus line, do not create a proposal (`CONFIGURATION_REQUIRED` is recorded on the skip audit). The shortage alert still exists.

`explanation` must include: source shelter id, resource type, latest quantity and unit, and that the item is a candidate for officer review. Wording stored for the UI is a message key plus parameters, not a hardcoded sentence that the client must display raw. Parameters: `source_shelter_name`, `resource_type`, `quantity`, `unit`.

## Endpoints

### `GET /api/v1/actions/` and `GET /api/v1/actions/{action_id}`

Permission: `action.read`. Query: `decision`, `shelter_id`, `block_id`, pagination.

Response includes source, destination, resource, suggested quantity, decision, explanation parameters, and status. It never includes a flag such as `auto_dispatch`.

### `POST /api/v1/actions/{action_id}/approve`

Permission: `action.approve` (District Officer). From `proposed` only. Event: `action.approved`. Status becomes `approved`. Optional note.

### `POST /api/v1/actions/{action_id}/modify`

Permission: `action.approve`. Body `ActionModify`: `quantity` ≥ 0 and optional note. From `proposed` only. Stores the officer’s quantity. Event: `action.modified`. Decision becomes `modified`, which is an approval of the modified quantity, not a system invention.

### `POST /api/v1/actions/{action_id}/reject`

Permission: `action.approve`. From `proposed` only. Event: `action.rejected`. No stock movement follows.

### `POST /api/v1/actions/{action_id}/confirm-receipt`

Permission: `action.confirm_receipt`. Caller must be the warden of `destination_shelter_id`. Allowed only when decision is `approved` or `modified`. Body: received `quantity` and `unit`. Event: `action.receipt_confirmed`. A later report from that warden remains the stock source of truth; this event records the confirmation the specification asks for and notifies the resources module to expect the next report. It does not silently add stock without a report. The receiving shelter still submits a report after receipt so the snapshot stays report-based.

| Failure | Status | Code |
| --- | --- | --- |
| Approve when already decided | 422 | `INVALID_STATE` |
| Confirm receipt before approval | 422 | `HUMAN_APPROVAL_REQUIRED` |
| Warden confirms a shelter that is not theirs | 404 | `NOT_FOUND` |
| Block officer calls approve | 403 | `PERMISSION_DENIED` |

There is no `/dispatch` or `/execute` route.

## AC-006

Given shelter A in shortage and shelter B with quantity above the approved surplus line, a proposed action lists B as `source_shelter_id` and A as `destination_shelter_id`.

## AC-007

The proposed action does not change B’s stock. Only approve, modify, or reject—each requiring `action.approve`—records the decision. A test calls a non-existent execute path and also asserts confirm-receipt before approval returns `HUMAN_APPROVAL_REQUIRED`.

## Tests

- No surplus configuration → no proposal.
- Reject leaves both snapshots unchanged.
- Explanation parameters present and no imperative “you must transfer” field.
