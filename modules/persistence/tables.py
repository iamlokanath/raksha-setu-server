import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base import Base, Identified, new_id
from common.timeutil import utcnow


class Tenant(Identified, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="active")


class Block(Identified, Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(64))


class User(Identified, Base):
    __tablename__ = "users"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    username: Mapped[str] = mapped_column(String(100), unique=True)
    role: Mapped[str] = mapped_column(String(32))
    organization: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grants: Mapped[list] = mapped_column(JSON, default=list)


class Assignment(Identified, Base):
    __tablename__ = "assignments"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    shelter_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    block_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    support_functions: Mapped[list] = mapped_column(JSON, default=list)


class RefreshToken(Identified, Base):
    __tablename__ = "refresh_tokens"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Shelter(Identified, Base):
    __tablename__ = "shelters"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    block_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(200))
    location_label: Mapped[str] = mapped_column(String(300))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    capacity: Mapped[int] = mapped_column(Integer)
    warden_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    reporting_contact: Mapped[str] = mapped_column(String(50))
    operational_status: Mapped[str] = mapped_column(String(32), default="active")
    current_status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_applied_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_population: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ShelterReport(Identified, Base):
    __tablename__ = "shelter_reports"
    __table_args__ = (UniqueConstraint("tenant_id", "client_report_id"),)
    client_report_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    shelter_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    population: Mapped[int] = mapped_column(Integer)
    children: Mapped[int] = mapped_column(Integer, default=0)
    older_adults: Mapped[int] = mapped_column(Integer, default=0)
    pregnant_women: Mapped[int] = mapped_column(Integer, default=0)
    persons_with_disability: Mapped[int] = mapped_column(Integer, default=0)
    injured_or_sick: Mapped[int] = mapped_column(Integer, default=0)
    food_quantity: Mapped[float] = mapped_column(Float)
    food_unit: Mapped[str] = mapped_column(String(32))
    water_quantity: Mapped[float] = mapped_column(Float)
    water_unit: Mapped[str] = mapped_column(String(32))
    medicine_quantity: Mapped[float] = mapped_column(Float)
    medicine_unit: Mapped[str] = mapped_column(String(32))
    incident_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="web")
    applied_to_current: Mapped[bool] = mapped_column(Boolean, default=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64))


class ResourceSnapshot(Identified, Base):
    __tablename__ = "resource_snapshots"
    __table_args__ = (UniqueConstraint("tenant_id", "shelter_id", "resource_type"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    shelter_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    resource_type: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResourceHistory(Identified, Base):
    __tablename__ = "resource_history"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    shelter_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    resource_type: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Alert(Identified, Base):
    __tablename__ = "alerts"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    shelter_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    type: Mapped[str] = mapped_column(String(32))
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    severity: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="detected")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cause_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class ActionRecord(Identified, Base):
    __tablename__ = "actions"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    source_shelter_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    destination_shelter_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    resource_type: Mapped[str] = mapped_column(String(32))
    suggested_quantity: Mapped[float] = mapped_column(Float)
    approved_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[str] = mapped_column(String(32), default="proposed")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    receipt_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation_key: Mapped[str] = mapped_column(String(100), default="action.explanation")
    explanation_params: Mapped[dict] = mapped_column(JSON, default=dict)


class AuditEvent(Identified, Base):
    __tablename__ = "audit_events"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), unique=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    aggregate_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Outbox(Base):
    __tablename__ = "outbox"
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    aggregate_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)


class SyncBatch(Identified, Base):
    __tablename__ = "sync_batches"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyncItem(Identified, Base):
    __tablename__ = "sync_items"
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    client_report_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    state: Mapped[str] = mapped_column(String(32), default="queued")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    body: Mapped[dict] = mapped_column(JSON)


class TenantConfiguration(Base):
    __tablename__ = "tenant_configurations"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    shortage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    capacity: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[dict | None] = mapped_column(JSON, nullable=True)
