# 01 — Architecture and Layering

## Runtime

Django is the HTTP application host: settings, middleware, URL routing, class-based views, and OpenAPI mounting.

SQLAlchemy is the persistence layer. Alembic is the only normal path for schema change. Django migrations are not used for domain tables.

PostgreSQL is the only primary database.

## Request path

```
HTTP
  → middleware (request id, authentication, tenant context)
  → class-based view
  → request schema validation
  → permission check
  → application service
  → repository
  → PostgreSQL
  → commit
  → outbox event
  → response schema
  → HTTP response
```

Event handlers run after commit. A handler may call services. A handler must not call views. A view must not call another view.

## Layer duties

| Layer | Allowed | Forbidden |
| --- | --- | --- |
| View (`controllers` / class-based API) | Parse HTTP, choose schema, call one service method, map result to status code and response schema | Business rules, queries, vendor SDK calls, direct status math |
| Schema | Declare fields, types, and structural constraints | Tenant lookups, alert transitions |
| Service | Use cases, domain rules, event registration inside the unit of work | HTTP objects, status-code selection |
| Repository | Tenant-scoped queries and writes | Permission policy, HTTP |
| Integration adapter | Provider SDK behind a port | Domain rules |

## Backend module layout

Each domain module uses the same internal shape:

```
modules/
├── auth/
│   ├── controllers/
│   ├── services/
│   ├── repositories/
│   ├── schemas/
│   ├── models/
│   ├── routes/
│   ├── events/
│   └── tests/
├── shelters/
├── reports/
├── resources/
├── alerts/
├── actions/
├── users/
├── tenants/
├── dashboard/
└── sync/
```

Shared infrastructure lives outside feature modules:

```
common/
├── api/            # BaseAPIView, error mapping, pagination
├── authz/          # principal, permission dependencies
├── db/             # session, unit of work
├── events/         # envelope, outbox, dispatcher
├── tenancy/        # tenant context
└── openapi/
integrations/
├── disha/
├── sso/
├── sms/
└── telephony/
migrations/         # Alembic
```

## Dependency direction

- `controllers` → `services` → `repositories` / `events`
- `alerts`, `resources`, and `dashboard` react to report events. They do not get imported by report controllers.
- Integration packages are imported only by the integrations module and by ports defined in domain services.

## File size and duplication

No source file may exceed 500 lines. Split by responsibility. A behaviour that already exists as a service, schema, or base view is reused.

## Configuration

Required environment names are documented in `.env.example` with empty or placeholder values:

- `DATABASE_URL`
- `SECRET_KEY`
- `ACCESS_TOKEN_TTL_SECONDS`
- `REFRESH_TOKEN_TTL_SECONDS`
- `CORS_ALLOWED_ORIGINS`
- `SSO_ISSUER` (optional until SSO is enabled)
- `SMS_PROVIDER` (empty until OD-004 is approved)
- `TELEPHONY_PROVIDER` (empty until OD-004 is approved)

Threshold and weight configuration is stored as approved tenant configuration rows, not as constants in Python.
