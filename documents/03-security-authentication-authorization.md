# 03 — Security, Authentication, and Authorization

## Default deny

Every `/api/v1/` route except the public list below requires a valid access token, a resolved tenant, and a permission check.

Public routes:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/docs`
- `GET /api/v1/schema`

Anything else added as public must be written into this list in the same change as the route.

## Authentication

The auth module issues application tokens through a port. Domain modules depend on the port (`Principal`), not on a vendor SDK. An SSO adapter (including a future DISHA integration) may satisfy the same port later without rewriting shelter, report, alert, or action services.

Baseline token behaviour until SSO is connected:

- Login accepts organization credentials and returns an access token and a refresh token.
- The client sends `Authorization: Bearer <access_token>`.
- Access tokens are short-lived. Refresh tokens rotate on use.
- Logout revokes the refresh token family.
- Missing, expired, malformed, or revoked tokens return `401` with `AUTH_INVALID`.
- Passwords are stored only as a slow hash. They are never logged, returned, or placed in events.

Token lifetimes are environment configuration (`ACCESS_TOKEN_TTL_SECONDS`, `REFRESH_TOKEN_TTL_SECONDS`), not literals scattered in views.

The access token carries: `user_id`, `tenant_id`, `role`, token id, issued-at, and expiry. It does not carry stock levels, reports, or personal notes.

## Principal

After authentication, middleware builds a `Principal`:

- `user_id`
- `tenant_id`
- `role`
- `shelter_id` when the user is bound to one shelter
- `block_id` when the user is bound to one block
- permission set

Services receive the principal. They do not re-parse JWTs.

## Roles

| Role | Scope in the specification |
| --- | --- |
| Shelter Warden | Own shelter information and reporting |
| Block Officer | Block-level review, validation, resource coordination |
| District Officer | District-level priority, relief-movement approval, unresolved alerts |
| Volunteer | Approved support functions only |
| Administrator permission | Shelter registration required by AC-001. This is the permission `shelter.register`, assigned explicitly. It is not implied by every district login. |

A user has one primary role and a permission set. Scope (shelter, block, or district) is data on the assignment, not a second hidden role.

## Permission catalogue

| Permission | Who may hold it |
| --- | --- |
| `shelter.register` | Explicit administrator assignment |
| `shelter.update` | Administrator assignment; District Officer for master data in their district |
| `shelter.read` | Any operational role, filtered by scope |
| `report.submit` | Warden for own shelter; Volunteer only when granted support reporting for that shelter |
| `report.read` | Operational roles, filtered by scope |
| `report.verify` | Block Officer |
| `resource.read` | Operational roles, filtered by scope |
| `alert.read` | Block Officer, District Officer; Warden for own shelter |
| `alert.acknowledge` | Block Officer, District Officer |
| `alert.plan` | Block Officer, District Officer |
| `alert.progress` | Block Officer, District Officer |
| `alert.resolve` | Block Officer, District Officer |
| `alert.close` | District Officer |
| `action.read` | Block Officer, District Officer; Warden reads actions that involve own shelter |
| `action.recommend` | System handlers only, not a client grant |
| `action.approve` | District Officer. This covers approve, modify, and reject of relief movement. |
| `action.confirm_receipt` | Warden of the receiving shelter |
| `dashboard.read` | Block Officer (block filter forced), District Officer (district) |
| `user.read` | District Officer within tenant; a user may read self via `/auth/me` |
| `user.manage` | Explicit administrator assignment inside the tenant |
| `audit.read` | District Officer |

Volunteer does not receive `action.approve`, `alert.close`, or `shelter.register` unless a later approved specification says so. OD-006 stays closed in the safe direction: no relief-approval rights.

## Scope rules

Authorization is two steps. Both must pass.

1. Permission bit.
2. Record scope:
   - Warden: `shelter_id` on the row equals the warden’s shelter.
   - Block Officer: shelter’s `block_id` equals the officer’s block.
   - District Officer: row `tenant_id` equals the officer’s tenant.
   - Volunteer: only shelters listed on the support assignment.

A row outside scope returns `404` when revealing that the id exists would leak another shelter’s presence inside a tenant the caller cannot fully see, and `403` with `PERMISSION_DENIED` when the caller can see the collection but not the action. Cross-tenant ids always return `404` so existence in another district is not confirmed.

## Transport and data protection

- TLS is required outside local development.
- CORS origins come from configuration.
- Responses omit password hashes, refresh tokens, and secrets.
- Vulnerable-group data is counts, not person-level records.
- Logs may contain request id, actor id, route, and status. Logs must not contain tokens, passwords, or full incident notes.
- Administrative and important operational actions append an audit record (see security document in module behaviour and document 09 references inside each module).

## Human-in-the-loop enforcement

No service method may set relief movement to an executed state unless an action is in `approved` or `modified` and the actor holds `action.approve`. System event handlers may create a recommendation in `proposed`. They must stop there.
