from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from common.timeutil import utcnow

EXTRA = ConfigDict(extra="forbid")
SUPPORT = Literal["reporting_support", "onboarding", "training", "verification", "local_coordination"]
ROLE = Literal["warden", "block_officer", "district_officer", "volunteer"]
GRANT = Literal["shelter.register", "user.manage", "tenant.manage"]


class LoginRequest(BaseModel):
    model_config = EXTRA
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    model_config = EXTRA
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    model_config = EXTRA
    refresh_token: str = Field(min_length=10)


class ResourceInput(BaseModel):
    model_config = EXTRA
    resource_type: Literal["food", "water", "medicine"]
    quantity: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=32)


class VulnerabilityInput(BaseModel):
    model_config = EXTRA
    children: int = Field(ge=0)
    older_adults: int = Field(ge=0)
    pregnant_women: int = Field(ge=0)
    persons_with_disability: int = Field(ge=0)
    injured_or_sick: int = Field(ge=0)

    def total(self) -> int:
        return self.children + self.older_adults + self.pregnant_women + self.persons_with_disability + self.injured_or_sick


class ReportCreate(BaseModel):
    model_config = EXTRA
    client_report_id: str
    shelter_id: str
    reported_at: str
    population: int = Field(ge=0)
    vulnerability: VulnerabilityInput
    resources: list[ResourceInput]
    incident_notes: str | None = Field(default=None, max_length=2000)
    channel: Literal["web"] = "web"

    @model_validator(mode="after")
    def check_report(self):
        from uuid import UUID
        from datetime import datetime

        UUID(self.client_report_id)
        UUID(self.shelter_id)
        reported = datetime.fromisoformat(self.reported_at.replace("Z", "+00:00"))
        if reported.tzinfo is None:
            raise ValueError("INVALID")
        if reported > utcnow() + timedelta(minutes=5):
            raise ValueError("FUTURE_TIMESTAMP")
        kinds = sorted(item.resource_type for item in self.resources)
        if kinds != ["food", "medicine", "water"] or len(self.resources) != 3:
            raise ValueError("RESOURCE_SET")
        if self.vulnerability.total() > self.population:
            raise ValueError("SUM_EXCEEDS_POPULATION")
        return self


class SyncBatchCreate(BaseModel):
    model_config = EXTRA
    reports: list[ReportCreate] = Field(min_length=1, max_length=50)


class PageQuery(BaseModel):
    model_config = EXTRA
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ShelterCreate(BaseModel):
    model_config = EXTRA
    name: str = Field(min_length=1, max_length=200)
    block_id: str
    location_label: str = Field(min_length=1, max_length=300)
    latitude: float | None = None
    longitude: float | None = None
    capacity: int = Field(ge=1)
    warden_user_id: str
    reporting_contact: str = Field(min_length=1, max_length=50)
    operational_status: Literal["active", "inactive"] = "active"

    @model_validator(mode="after")
    def coordinates(self):
        pair = (self.latitude is None, self.longitude is None)
        if pair[0] != pair[1]:
            raise ValueError("COORDINATES")
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise ValueError("INVALID")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValueError("INVALID")
        return self


class ShelterUpdate(BaseModel):
    model_config = EXTRA
    name: str | None = Field(default=None, min_length=1, max_length=200)
    block_id: str | None = None
    location_label: str | None = Field(default=None, min_length=1, max_length=300)
    latitude: float | None = None
    longitude: float | None = None
    capacity: int | None = Field(default=None, ge=1)
    warden_user_id: str | None = None
    reporting_contact: str | None = Field(default=None, min_length=1, max_length=50)
    operational_status: Literal["active", "inactive"] | None = None

    @model_validator(mode="after")
    def at_least_one(self):
        if not self.model_fields_set:
            raise ValueError("REQUIRED")
        return self


class ShelterListQuery(PageQuery):
    operational_status: Literal["active", "inactive"] | None = None
    block_id: str | None = None
    sort: Literal["name", "current_status"] = "name"


class ReportListQuery(PageQuery):
    shelter_id: str | None = None
    channel: Literal["web", "sms", "telephony"] | None = None
    sort: Literal["reported_at"] = "reported_at"
    from_time: str | None = Field(default=None, alias="from")
    to_time: str | None = Field(default=None, alias="to")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AlertTransition(BaseModel):
    model_config = EXTRA
    note: str | None = Field(default=None, max_length=1000)


class AlertListQuery(PageQuery):
    status: str | None = None
    severity: Literal["attention", "urgent"] | None = None
    type: Literal["shortage", "capacity"] | None = None
    block_id: str | None = None
    shelter_id: str | None = None
    sort: Literal["created_at", "severity"] = "created_at"


class ActionDecision(BaseModel):
    model_config = EXTRA
    note: str | None = Field(default=None, max_length=1000)


class ActionModify(BaseModel):
    model_config = EXTRA
    quantity: float = Field(ge=0)
    note: str | None = Field(default=None, max_length=1000)


class ReceiptBody(BaseModel):
    model_config = EXTRA
    quantity: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=32)


class ActionListQuery(PageQuery):
    decision: Literal["proposed", "approved", "modified", "rejected"] | None = None
    shelter_id: str | None = None
    block_id: str | None = None


class UserCreate(BaseModel):
    model_config = EXTRA
    name: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    role: ROLE
    organization: str = Field(min_length=1, max_length=200)
    shelter_id: str | None = None
    block_id: str | None = None
    support_functions: list[SUPPORT] = Field(default_factory=list)
    grants: list[GRANT] = Field(default_factory=list)

    @model_validator(mode="after")
    def assignment_shape(self):
        if self.role == "warden" and (not self.shelter_id or self.block_id or self.support_functions or self.grants):
            raise ValueError("ASSIGNMENT")
        if self.role == "block_officer" and (not self.block_id or self.shelter_id or self.support_functions or self.grants):
            raise ValueError("ASSIGNMENT")
        if self.role == "district_officer" and (self.shelter_id or self.block_id or self.support_functions):
            raise ValueError("ASSIGNMENT")
        if self.role == "volunteer" and (self.grants or not self.support_functions or bool(self.shelter_id) == bool(self.block_id)):
            raise ValueError("ASSIGNMENT")
        return self


class UserUpdate(BaseModel):
    model_config = EXTRA
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: ROLE | None = None
    organization: str | None = None
    status: Literal["active", "inactive"] | None = None
    shelter_id: str | None = None
    block_id: str | None = None
    support_functions: list[SUPPORT] | None = None
    grants: list[GRANT] | None = None

    @model_validator(mode="after")
    def at_least_one(self):
        if not self.model_fields_set:
            raise ValueError("REQUIRED")
        return self


class UserListQuery(PageQuery):
    role: ROLE | None = None
    block_id: str | None = None
    shelter_id: str | None = None


class TenantCreate(BaseModel):
    model_config = EXTRA
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=64)


class BlockCreate(BaseModel):
    model_config = EXTRA
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=64)


class ResourceRule(BaseModel):
    model_config = EXTRA
    attention_below: float = Field(ge=0)
    urgent_below: float = Field(ge=0)
    surplus_above: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def order(self):
        if not self.attention_below > self.urgent_below:
            raise ValueError("THRESHOLD_ORDER")
        return self


class ShortageConfig(BaseModel):
    model_config = EXTRA
    food: ResourceRule
    water: ResourceRule
    medicine: ResourceRule


class CapacityConfig(BaseModel):
    model_config = EXTRA
    attention_at_ratio: float = Field(gt=0)
    urgent_at_ratio: float = Field(gt=0)

    @model_validator(mode="after")
    def order(self):
        if not self.urgent_at_ratio > self.attention_at_ratio:
            raise ValueError("THRESHOLD_ORDER")
        return self


class PriorityConfig(BaseModel):
    model_config = EXTRA
    weights: dict[str, float]
    vulnerable_cap: float = Field(gt=0)
    age_cap_hours: float = Field(gt=0)
    severity_scores: dict[str, float]
    bands: dict[str, float]

    @model_validator(mode="after")
    def shape(self):
        expected = {"shortage_urgency", "vulnerable_population", "occupancy_pressure", "issue_age"}
        if set(self.weights) != expected or any(value < 0 for value in self.weights.values()):
            raise ValueError("WEIGHTS")
        if set(self.severity_scores) != {"none", "attention", "urgent"}:
            raise ValueError("SEVERITY_SCORES")
        if set(self.bands) != {"high", "medium"} or not self.bands["high"] > self.bands["medium"] > 0:
            raise ValueError("BANDS")
        return self


class ConfigurationBody(BaseModel):
    model_config = EXTRA
    shortage: ShortageConfig | None = None
    capacity: CapacityConfig | None = None
    priority: PriorityConfig | None = None


class DashboardShelterQuery(PageQuery):
    status: Literal["green", "yellow", "red", "unknown"] | None = None
    block_id: str | None = None
    shortage_type: Literal["food", "water", "medicine"] | None = None
    occupancy: Literal["below_attention", "attention", "urgent", "unknown"] | None = None
    priority: Literal["high", "medium", "low", "unscored"] | None = None


class ResourceListQuery(PageQuery):
    block_id: str | None = None
    resource_type: Literal["food", "water", "medicine"] | None = None
    surplus: bool | None = None

    @field_validator("surplus", mode="before")
    @classmethod
    def parse_surplus(cls, value):
        if value in (None, ""):
            return None
        if value in (True, False):
            return value
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError("INVALID")


class AuditListQuery(PageQuery):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_time: str | None = Field(default=None, alias="from")
    to_time: str | None = Field(default=None, alias="to")
    event_type: str | None = None
    aggregate_id: str | None = None
