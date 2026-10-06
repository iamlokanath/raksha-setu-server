# Module — Sync and Offline

Specification: §§8–9, 23. Acceptance: AC-003.

## Responsibility

Accept reports captured without connectivity, detect duplicates, and stop an older report from overwriting newer shelter information. Alternative channels enter through the same report service after the integration adapter maps them.

## Client contract

The warden’s device stores reports locally. Each stored report already has `client_report_id` and `reported_at` from capture time, not from sync time. The server’s `received_at` is the ingest time.

### `POST /api/v1/sync/reports`

Permission: `report.submit`. Class-based view `SyncBatchCreateView`.

Request `SyncBatchCreate`:

```json
{
  "reports": [ { "same fields as ReportCreate": true } ]
}
```

Maximum 50 reports per request. Each item is schema-validated. One invalid item rejects the whole batch with `400` and `details[].field` set to `reports[index].<field>`. Nothing is queued.

Success: the batch row and item rows commit, event `sync.batch_accepted`, HTTP `202`, body contains `batch_id` and `accepted_count`.

Processing handler:

| Item case | Result state | Report event |
| --- | --- | --- |
| New id, `reported_at` is newest | `applied` | `report.submitted` |
| New id, older than current snapshot | `stored_historical` | `report.stored_historical` |
| Known id, same payload | `duplicate` | `report.duplicate_ignored` |
| Known id, different payload | `rejected` | none; item error `DUPLICATE_MISMATCH` |

The HTTP `202` means the batch is durable, not that every item applied. Clients poll:

### `GET /api/v1/sync/batches/{batch_id}`

Permission: `report.submit` and the batch actor is the caller, or `report.read` for an officer in scope. Returns per-item state and error code. `404` if the batch is outside scope.

## Conflict policy (baseline for OD-005)

This is the full automatic policy until a richer merge is approved:

1. Identity is `client_report_id` inside the tenant.
2. Identical retries are duplicates and do not double-apply.
3. A different body for the same id is a conflict and does not apply.
4. Among different ids, only a report with `reported_at` greater than or equal to `last_applied_report_at` updates the current snapshot.
5. Older reports remain readable history.

No field-by-field merge. No “last writer wins” based on arrival order.

## Alternative channels

SMS and automated-call adapters may call the report service with `channel` set accordingly and a synthetic `client_report_id` derived from provider message id (stable, so retries dedupe). They are not extra shelter records. Officers still read one shelter.

If the provider is not approved (OD-004), the adapter is unbound and those ingress routes are not registered. Absence of the provider does not remove web sync.

## Network-failure mitigation

The server assumes the client kept the queue. It offers batch ingest, idempotency, and item-level results. It does not require the phone to be online at the moment of capture.

## Tests (AC-003)

- Submit a batch with no dependency on a live client network: items persist and a later processor applies them.
- Replay of the same batch does not create a second applied snapshot.
- An older `reported_at` does not change current food quantity.
- A newer report then an older replay leaves the newer quantity in place.
- Item schema error returns `400` and an empty outbox.
