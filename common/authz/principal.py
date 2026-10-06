from dataclasses import dataclass, field
from uuid import UUID


ROLE_PERMISSIONS = {
    "warden": {
        "shelter.read",
        "report.submit",
        "report.read",
        "resource.read",
        "alert.read",
        "action.read",
        "action.confirm_receipt",
    },
    "block_officer": {
        "shelter.read",
        "report.read",
        "report.verify",
        "resource.read",
        "alert.read",
        "alert.acknowledge",
        "alert.plan",
        "alert.progress",
        "alert.resolve",
        "action.read",
        "dashboard.read",
    },
    "district_officer": {
        "shelter.read",
        "shelter.update",
        "report.read",
        "report.verify",
        "resource.read",
        "alert.read",
        "alert.acknowledge",
        "alert.plan",
        "alert.progress",
        "alert.resolve",
        "alert.close",
        "action.read",
        "action.approve",
        "dashboard.read",
        "user.read",
        "audit.read",
    },
    "volunteer": {"shelter.read", "report.read", "resource.read"},
}

EXPLICIT_GRANTS = {"shelter.register", "user.manage", "tenant.manage"}


@dataclass
class Principal:
    user_id: UUID
    tenant_id: UUID
    role: str
    shelter_id: UUID | None
    block_id: UUID | None
    permissions: set[str] = field(default_factory=set)
    support_functions: list[str] = field(default_factory=list)
    status: str = "active"

    def allows(self, permission: str) -> bool:
        return permission in self.permissions


def permissions_for(role: str, support_functions: list[str], grants: list[str]) -> set[str]:
    found = set(ROLE_PERMISSIONS.get(role, set()))
    if role == "volunteer" and "reporting_support" in support_functions:
        found.add("report.submit")
    for grant in grants or []:
        if grant in EXPLICIT_GRANTS:
            found.add(grant)
    return found
