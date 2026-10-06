# 00 — SDD Baseline

## Purpose

Raksha Setu is a district-level emergency shelter coordination and relief-resource visibility system. It is decision support. Human officers remain responsible for approving high-impact actions such as relief movement and medicine redirection.

The approved specification is the source of truth for API behaviour, data models, validation, permissions, error handling, tests, and integrations.

Requirement flow:

1. Business requirement
2. Specification ID / rule
3. Implementation
4. Unit / integration / acceptance tests
5. Specification compliance verification

## Traceability

Every significant feature keeps this chain:

Requirement ID → specification rule → technical design (this document set) → module → unit tests → integration tests → acceptance criteria → pilot validation.

Acceptance criteria IDs are AC-001 through AC-010. Module documents cite the IDs they satisfy.

## Approved technical decisions for this API

The SOP names the stack. This implementation baseline adds the following API decisions, which are now mandatory:

| Decision | Rule |
| --- | --- |
| API style | REST only for application clients. No ad-hoc RPC paths. |
| Handler style | Class-based views only. Function-based application endpoints are not allowed. |
| Namespace | `/api/v1/{module}/` |
| Documentation | Every endpoint is in OpenAPI and Swagger UI before it is considered done. |
| Protection | Authenticated and authorized by default. A public endpoint needs an explicit entry in the auth module. |
| Schemas | Every request and response has a named schema. Controllers do not accept untyped bodies. |
| Validation | Schema validation, then domain validation. Failures use the error contract in document 04. |
| Status codes | Use only the codes defined in document 04. |
| Events | Every successful state-changing API publishes a domain event after commit. Read models and side effects subscribe to events. |
| Tenancy | Enforced in repositories. District is the tenant. See document 07. |
| Persistence | PostgreSQL, SQLAlchemy models, Alembic migrations. Django ORM is not the system of record. |
| Secrets | Environment variables only. `.env.example` lists names and never real secrets. |

## In scope

Shelter registration, shelter reporting, population and vulnerability counts, food/water/medicine monitoring, shortage and capacity warnings, alerts, redistribution suggestions, priority factors, human approval, offline sync, SMS and automated-call intake behind integration boundaries, history, role-based access, and audit.

## Out of scope until a later approved specification

- A final SMS or telephony provider
- Exact priority-score weights
- Exact stock thresholds and the shortage prediction formula
- Any business rule not written in the SOP or in this document set
- Autonomous dispatch of relief or medicine

## Open decisions

These values must be written down and approved before production behaviour depends on them. Code must read them from configuration. Code must not embed a guessed number and present it as policy.

| ID | Topic | Until approved |
| --- | --- | --- |
| OD-001 | Shortage thresholds and prediction formula | Do not raise a shortage alert. Persist the reported quantities. |
| OD-002 | Capacity warning thresholds | Do not raise a capacity alert. Persist population and capacity. |
| OD-003 | Priority weights | Return the four required factors. Do not return an official numeric score. |
| OD-004 | SMS and telephony provider | Expose the integration port only. Do not call a vendor SDK from a domain module. |
| OD-005 | Field-level merge beyond “older report must not overwrite newer information” | Apply the baseline conflict policy in the sync module only. |
| OD-006 | Exact volunteer permission flags beyond approved support functions | Grant no relief-approval permission to volunteers. |

## Non-negotiable rules that bind this service

- No hardcoded secrets.
- No business logic in API controller classes beyond transport mapping.
- No unprotected application endpoint unless listed as public.
- No cross-tenant data access.
- No undocumented API.
- No feature without tests.
- No autonomous high-impact relief action.
- No implementation that contradicts the approved specification.
- No guessed thresholds, weights, or providers.
