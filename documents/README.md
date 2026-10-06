# Raksha Setu Server — Specification Index

Source of truth: Raksha Setu Software Specification & SDD Engineering SOP, Version 1.0, plus the API decisions recorded in [00-sdd-baseline.md](00-sdd-baseline.md).

These documents define behaviour, contracts, permissions, events, validation, and tests. They do not approve visual design, stock thresholds, priority weights, or an SMS/telephony provider.

## How to read this set

1. Read the baseline and the cross-cutting standards before any module.
2. Read the module that you are implementing, including its events, schemas, status codes, and acceptance links.
3. Treat a feature as incomplete until its acceptance criteria and tests in [08-testing-and-acceptance.md](08-testing-and-acceptance.md) pass.

## Standards

| Document | Covers |
| --- | --- |
| [00-sdd-baseline.md](00-sdd-baseline.md) | Purpose, traceability, approved decisions, open decisions |
| [01-architecture-and-layering.md](01-architecture-and-layering.md) | Django host, layers, module layout |
| [02-rest-and-class-based-api.md](02-rest-and-class-based-api.md) | REST rules, class-based views, OpenAPI, resource map |
| [03-security-authentication-authorization.md](03-security-authentication-authorization.md) | Authentication, roles, permissions, default-deny |
| [04-schemas-validation-and-errors.md](04-schemas-validation-and-errors.md) | Schema rules, validation, status codes, error body |
| [05-event-driven-model.md](05-event-driven-model.md) | Domain events, outbox, handlers, idempotency |
| [06-data-model-and-database.md](06-data-model-and-database.md) | Entities, persistence, Alembic |
| [07-multi-tenancy.md](07-multi-tenancy.md) | District tenant boundary and scope filters |
| [08-testing-and-acceptance.md](08-testing-and-acceptance.md) | Test matrix and AC-001–AC-010 |

## Modules

| Document | Spec sections |
| --- | --- |
| [modules/auth.md](modules/auth.md) | §§21–22, 31–32 |
| [modules/shelters.md](modules/shelters.md) | §5, AC-001 |
| [modules/reports.md](modules/reports.md) | §§6–7, AC-002 |
| [modules/resources.md](modules/resources.md) | §§11–13 |
| [modules/alerts.md](modules/alerts.md) | §14, AC-004, AC-008 |
| [modules/actions.md](modules/actions.md) | §§15–16, AC-006, AC-007 |
| [modules/users.md](modules/users.md) | §§4, 22 |
| [modules/tenants.md](modules/tenants.md) | §§24, 31 |
| [modules/dashboard-and-priority.md](modules/dashboard-and-priority.md) | §§17–19, AC-005, AC-009 |
| [modules/sync-and-offline.md](modules/sync-and-offline.md) | §§8–9, AC-003 |
| [modules/integrations.md](modules/integrations.md) | §§9, 32 |
| [modules/audit.md](modules/audit.md) | §§21, AC-010 |
