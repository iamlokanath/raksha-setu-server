# 02 — REST and Class-Based API

## REST rules

- Resources are nouns. Actions that are not CRUD are sub-resources with a verb that names an approved business transition, for example `POST /api/v1/alerts/{id}/acknowledge`.
- Use HTTP methods for their standard meaning.
- `GET` is safe and does not change shelter operational state.
- `POST` creates a resource or requests a named transition.
- `PATCH` partially updates a resource.
- `PUT` is reserved for full replacement and is not used unless a module spec says so.
- `DELETE` is not used for alerts, reports, or actions. Those records are historical. Closure is a status transition.
- Collection responses are paginated.
- Filtering and sorting use query parameters defined on that endpoint’s schema.
- Clients send and receive JSON. `Content-Type` and `Accept` are `application/json`.

## Versioning

All application routes sit under `/api/v1/`. A breaking change requires a new version. Adding an optional response field is non-breaking. Removing or renaming a field is breaking.

Approved namespaces:

- `/api/v1/auth/`
- `/api/v1/shelters/`
- `/api/v1/reports/`
- `/api/v1/resources/`
- `/api/v1/alerts/`
- `/api/v1/actions/`
- `/api/v1/users/`
- `/api/v1/tenants/`
- `/api/v1/dashboard/`
- `/api/v1/sync/`
- `/api/v1/audit/`

## Class-based API

Every application endpoint is a method on a class that extends one project base:

| Base class | Use |
| --- | --- |
| `PublicAPIView` | Only endpoints listed as public in the auth module |
| `AuthenticatedAPIView` | Any signed-in user, still tenant-scoped |
| `PermissionAPIView` | Declares `required_permission` |
| `TenantScopedAPIView` | Default parent for domain endpoints; includes authentication, tenant, and permission |

A view class declares:

- `request_schema` when the method has a body
- `query_schema` when the method has query parameters
- `response_schema`
- `required_permission` when access is narrower than “any authenticated user in the tenant”
- one service method call per action method

Illustrative shape (transport only):

```python
class ShelterReportCreateView(TenantScopedAPIView):
    request_schema = ShelterReportCreateSchema
    response_schema = ShelterReportResponseSchema
    required_permission = "report.submit"

    def post(self, request):
        command = self.parse_body()
        result = report_service.submit(self.principal, command)
        return self.respond(result)
```

`self.respond` maps a service result to the status code defined by that use case. The view does not recalculate shelter status, open alerts, or approve relief.

Function-based views are forbidden for `/api/v1/` application routes. Shared behaviour belongs on the base class, not in a copied helper inside each module.

## OpenAPI

- Schemas in code are the source for the OpenAPI document.
- Swagger UI is served at `/api/v1/docs`.
- The schema document is served at `/api/v1/schema`.
- Each operation documents method, path, permission, parameters, request schema, response schema, error responses, status codes, and an example.
- An endpoint missing from the schema fails the module’s definition of done.

`/api/v1/docs` and `/api/v1/schema` are public read-only documentation endpoints. They must not return live tenant data.

## Resource map

Detailed fields live in the module documents. This is the route index.

| Method | Path | Permission | Success |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | public | 200 |
| POST | `/api/v1/auth/refresh` | public, valid refresh token | 200 |
| POST | `/api/v1/auth/logout` | authenticated | 204 |
| GET | `/api/v1/auth/me` | authenticated | 200 |
| POST | `/api/v1/shelters/` | `shelter.register` | 201 |
| GET | `/api/v1/shelters/` | `shelter.read` | 200 |
| GET | `/api/v1/shelters/{shelter_id}` | `shelter.read` | 200 |
| PATCH | `/api/v1/shelters/{shelter_id}` | `shelter.update` | 200 |
| POST | `/api/v1/reports/` | `report.submit` | 201 |
| GET | `/api/v1/reports/` | `report.read` | 200 |
| GET | `/api/v1/reports/{report_id}` | `report.read` | 200 |
| GET | `/api/v1/shelters/{shelter_id}/reports` | `report.read` | 200 |
| POST | `/api/v1/sync/reports` | `report.submit` | 202 |
| GET | `/api/v1/shelters/{shelter_id}/resources` | `resource.read` | 200 |
| GET | `/api/v1/resources/` | `resource.read` | 200 |
| GET | `/api/v1/alerts/` | `alert.read` | 200 |
| GET | `/api/v1/alerts/{alert_id}` | `alert.read` | 200 |
| POST | `/api/v1/alerts/{alert_id}/acknowledge` | `alert.acknowledge` | 200 |
| POST | `/api/v1/alerts/{alert_id}/plan` | `alert.plan` | 200 |
| POST | `/api/v1/alerts/{alert_id}/start` | `alert.progress` | 200 |
| POST | `/api/v1/alerts/{alert_id}/resolve` | `alert.resolve` | 200 |
| POST | `/api/v1/alerts/{alert_id}/close` | `alert.close` | 200 |
| GET | `/api/v1/actions/` | `action.read` | 200 |
| GET | `/api/v1/actions/{action_id}` | `action.read` | 200 |
| POST | `/api/v1/actions/{action_id}/approve` | `action.approve` | 200 |
| POST | `/api/v1/actions/{action_id}/modify` | `action.approve` | 200 |
| POST | `/api/v1/actions/{action_id}/reject` | `action.approve` | 200 |
| POST | `/api/v1/actions/{action_id}/confirm-receipt` | `action.confirm_receipt` | 200 |
| GET | `/api/v1/users/` | `user.read` | 200 |
| POST | `/api/v1/users/` | `user.manage` | 201 |
| PATCH | `/api/v1/users/{user_id}` | `user.manage` | 200 |
| GET | `/api/v1/dashboard/summary` | `dashboard.read` | 200 |
| GET | `/api/v1/dashboard/shelters` | `dashboard.read` | 200 |
| GET | `/api/v1/audit/` | `audit.read` | 200 |

There is no endpoint that dispatches relief or redirects medicine without an approved action record.

## Idempotency

State-changing creates that clients may retry (`POST /reports/`, `POST /sync/reports`) require a client-generated UUID. Replaying the same UUID with the same payload returns the original result and does not append a second operational report. The same UUID with a different payload returns `409`.

## Pagination, filtering, sorting

List endpoints accept:

- `page` (default 1, minimum 1)
- `page_size` (default 20, maximum 100)
- `sort` limited to fields named in that module

Unknown query fields fail validation with `400`.
