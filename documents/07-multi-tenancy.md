# 07 — Multi-Tenancy

## Tenant boundary

A tenant is a district. This matches the required path from a one-block pilot, to a district, to later multi-district deployment. A block is a scope inside the tenant, not a separate tenant.

A user belongs to one tenant. A shelter belongs to one tenant. Reports, resources, alerts, actions, and audit rows carry the same `tenant_id` as their shelter.

## Enforcement

- The access token’s `tenant_id` is the only tenant a request may use.
- Clients may not pass `tenant_id` in a body to switch context. If they send it, it must equal the token tenant or the request fails with `403` and `PERMISSION_DENIED`.
- Every repository query includes `tenant_id` from the principal. There is no “unscoped” repository method in domain modules.
- Cross-tenant reads and writes return `404` and `NOT_FOUND`.
- Event handlers carry `tenant_id` from the envelope and open their database work with that tenant. A handler must not process an event under a different tenant session.
- Background dispatch still sets tenant context explicitly. It does not run as a superuser that can see all districts by default.

## Pilot shape

The first pilot may contain one tenant and one block. The schema and queries still include `tenant_id` and `block_id` so later shelters do not require a rewrite.

## Tests that must exist

- User in tenant A cannot read or write tenant B’s shelter, report, alert, or action, including by guessing ids.
- A list endpoint never returns mixed `tenant_id` values.
- An event created in tenant A does not update a read model row in tenant B.
