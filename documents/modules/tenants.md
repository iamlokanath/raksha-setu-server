# Module — Tenants

Specification: §§24, 31. Boundary rules: document 07.

## Responsibility

Register a district tenant and its blocks so shelters can be attached without an application rebuild. Tenant administration is not a shelter-warden feature.

## Endpoints

These routes use class-based views and the same error envelope. They are still under `/api/v1/tenants/`.

### `POST /api/v1/tenants/`

Allowed only for a platform operator identified by the environment-configured bootstrap credential, documented as a public-exception alternative: it is **not** public. The operator presents the normal bearer token of a user with `tenant.manage`, which is not granted inside a district role. Seed the first operator out of band. Document the seed step in operations notes without putting the secret in the repository.

Request: `name`, `code`. Success: `201`. The creator’s token tenant is not overwritten.

### `POST /api/v1/tenants/{tenant_id}/blocks`

Permission: `tenant.manage` or the tenant’s `user.manage` for their own tenant. Request: `name`, `code`. Block codes are unique per tenant.

### `GET /api/v1/tenants/{tenant_id}`

Caller’s token tenant must match `tenant_id`, unless the caller has `tenant.manage`. Otherwise `404`.

## Pilot

Weeks 1–2 produce a pilot tenant, at least one block, the shelter registry, and user roles. That work uses these endpoints plus the shelter and user modules.

## Tests

A district officer cannot create a second tenant. A block created in tenant A is invisible to tenant B’s shelter create (the block id yields `404`).
