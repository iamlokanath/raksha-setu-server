def build_schema() -> dict:
    paths = {
        "/api/v1/auth/login": {"post": _op("Login", public=True)},
        "/api/v1/auth/refresh": {"post": _op("Refresh", public=True)},
        "/api/v1/auth/logout": {"post": _op("Logout")},
        "/api/v1/auth/me": {"get": _op("Current principal")},
        "/api/v1/tenants/": {"post": _op("Create tenant", permission="tenant.manage")},
        "/api/v1/tenants/{tenant_id}": {"get": _op("Get tenant")},
        "/api/v1/tenants/{tenant_id}/blocks": {"post": _op("Create block")},
        "/api/v1/tenants/{tenant_id}/configuration": {
            "get": _op("Read warning configuration"),
            "put": _op("Save warning configuration"),
        },
        "/api/v1/users/": {"get": _op("List users", permission="user.read"), "post": _op("Create user", permission="user.manage")},
        "/api/v1/users/{user_id}": {"patch": _op("Update user", permission="user.manage")},
        "/api/v1/shelters/": {"get": _op("List shelters", permission="shelter.read"), "post": _op("Register shelter", permission="shelter.register")},
        "/api/v1/shelters/{shelter_id}": {"get": _op("Get shelter", permission="shelter.read"), "patch": _op("Update shelter", permission="shelter.update")},
        "/api/v1/shelters/{shelter_id}/reports": {"get": _op("List shelter reports", permission="report.read")},
        "/api/v1/shelters/{shelter_id}/resources": {"get": _op("Shelter stock", permission="resource.read")},
        "/api/v1/reports/": {"get": _op("List reports", permission="report.read"), "post": _op("Submit report", permission="report.submit")},
        "/api/v1/reports/{report_id}": {"get": _op("Get report", permission="report.read")},
        "/api/v1/resources/": {"get": _op("List resources", permission="resource.read")},
        "/api/v1/alerts/": {"get": _op("List alerts", permission="alert.read")},
        "/api/v1/alerts/{alert_id}": {"get": _op("Get alert", permission="alert.read")},
        "/api/v1/alerts/{alert_id}/acknowledge": {"post": _op("Acknowledge alert", permission="alert.acknowledge")},
        "/api/v1/alerts/{alert_id}/plan": {"post": _op("Plan alert action", permission="alert.plan")},
        "/api/v1/alerts/{alert_id}/start": {"post": _op("Start alert action", permission="alert.progress")},
        "/api/v1/alerts/{alert_id}/resolve": {"post": _op("Resolve alert", permission="alert.resolve")},
        "/api/v1/alerts/{alert_id}/close": {"post": _op("Close alert", permission="alert.close")},
        "/api/v1/actions/": {"get": _op("List actions", permission="action.read")},
        "/api/v1/actions/{action_id}": {"get": _op("Get action", permission="action.read")},
        "/api/v1/actions/{action_id}/approve": {"post": _op("Approve redistribution", permission="action.approve")},
        "/api/v1/actions/{action_id}/modify": {"post": _op("Modify redistribution", permission="action.approve")},
        "/api/v1/actions/{action_id}/reject": {"post": _op("Reject redistribution", permission="action.approve")},
        "/api/v1/actions/{action_id}/confirm-receipt": {"post": _op("Confirm receipt", permission="action.confirm_receipt")},
        "/api/v1/dashboard/summary": {"get": _op("Dashboard summary", permission="dashboard.read")},
        "/api/v1/dashboard/shelters": {"get": _op("Dashboard shelters", permission="dashboard.read")},
        "/api/v1/sync/reports": {"post": _op("Accept offline batch", permission="report.submit")},
        "/api/v1/sync/batches/{batch_id}": {"get": _op("Sync batch status")},
        "/api/v1/audit/": {"get": _op("Audit history", permission="audit.read")},
    }
    return {
        "openapi": "3.0.3",
        "info": {"title": "Raksha Setu API", "version": "1.0.0"},
        "paths": paths,
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string"},
                                "details": {"type": "array"},
                                "request_id": {"type": "string"},
                            },
                        }
                    },
                }
            },
        },
    }


def _op(summary: str, permission: str | None = None, public: bool = False) -> dict:
    operation = {
        "summary": summary,
        "responses": {
            "200": {"description": "Success"},
            "400": {"description": "Validation error"},
            "401": {"description": "Authentication failed"},
            "403": {"description": "Permission denied"},
            "404": {"description": "Not found"},
            "409": {"description": "Conflict"},
            "422": {"description": "Business rule failure"},
            "500": {"description": "Internal error"},
        },
    }
    if permission:
        operation["description"] = f"Requires {permission}."
    if not public:
        operation["security"] = [{"bearerAuth": []}]
    return operation
