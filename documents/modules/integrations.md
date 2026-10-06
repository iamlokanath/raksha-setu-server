# Module — Integrations

Specification: §§9, 32. Open decision OD-004.

## Responsibility

Isolate provider SDKs so DISHA, SSO, SMS, and telephony can be replaced without editing shelter, report, alert, or action services.

```
integrations/
├── disha/
├── sso/
├── sms/
└── telephony/
```

Each package exposes a port and an adapter. Domain modules import the port only.

## Ports

| Port | Methods | Domain effect |
| --- | --- | --- |
| `SsoAuthenticationProvider` | exchange external identity → local user id | auth module issues the same application tokens |
| `InboundMessagePort` | normalized `channel`, `provider_message_id`, shelter code, counts, quantities, observed time | sync/report service |
| `OutboundNotificationPort` | optional later; not required to satisfy the current acceptance criteria | none until specified |

Inbound mapping rules:

- Resolve shelter by tenant and a pre-registered channel address on the shelter (`reporting_contact` or an approved alias table). Unknown sender: do not create a shelter. Record a failed ingest audit and return a provider-appropriate acknowledgement without writing a report.
- Build `client_report_id` as a UUIDv5 of tenant id + provider + provider message id so retries dedupe.
- Pass the normalized command into the report service. Do not open a second code path that writes SQL.

## Provider absence

`SMS_PROVIDER` and `TELEPHONY_PROVIDER` empty means the adapters are not constructed and no inbound webhook route is mounted. Web and sync APIs stay available.

Webhook routes, when a provider is approved, are class-based, versioned under `/api/v1/integrations/{provider}/inbound`, authenticated by the provider’s documented signature, and listed in document 03’s public-exception section only if they cannot use a bearer token. Signature failure is `401`.

## DISHA and SSO

User, role, and workflow code must not import a DISHA client. The SSO adapter may provision a user assignment only through the user service. It must not bypass permissions.

## Tests

- Adapter unit test with a fake provider payload creates one report through the service.
- Duplicate provider delivery creates one report.
- Unknown sender creates zero reports.
- Domain packages contain no import of a vendor SDK (test by import boundary or package lint).

## Privacy

Inbound payloads logged for debug must be redacted. Store the normalized report, not the raw telecom body, unless an approved audit need says otherwise. Default is to store provider message id only.
