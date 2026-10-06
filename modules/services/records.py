import uuid

from common.api.errors import ApiError
from common.authz.passwords import hash_password
from common.events.bus import publish
from common.timeutil import utcnow
from modules.persistence.tables import (
    ActionRecord,
    Alert,
    Assignment,
    Block,
    Shelter,
    SyncBatch,
    SyncItem,
    Tenant,
    TenantConfiguration,
    User,
)
from modules.presenters import action_out, alert_out, shelter_out, user_out
from modules.services.scope import block_in_tenant, parse_uuid, shelter_or_404, user_in_tenant

TRANSITIONS = {
    "acknowledge": ("detected", "acknowledged", "alert.acknowledged"),
    "plan": ("acknowledged", "action_planned", "alert.action_planned"),
    "start": ("action_planned", "action_in_progress", "alert.action_in_progress"),
    "resolve": ("action_in_progress", "resolved", "alert.resolved"),
    "close": ("resolved", "closed", "alert.closed"),
}


def _event(session, principal, request_id, event_type, aggregate_type, aggregate_id, payload=None):
    publish(
        session,
        event_type=event_type,
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload or {},
        request_id=request_id,
    )


def create_shelter(session, principal, data, request_id):
    block = block_in_tenant(session, principal, parse_uuid(data.block_id, "block_id"))
    warden = user_in_tenant(session, principal, parse_uuid(data.warden_user_id, "warden_user_id"))
    if warden.role != "warden":
        raise ApiError(404, "NOT_FOUND")
    shelter = Shelter(
        tenant_id=principal.tenant_id,
        block_id=block.id,
        name=data.name,
        location_label=data.location_label,
        latitude=data.latitude,
        longitude=data.longitude,
        capacity=data.capacity,
        warden_user_id=warden.id,
        reporting_contact=data.reporting_contact,
        operational_status=data.operational_status,
        current_status="unknown",
    )
    session.add(shelter)
    session.flush()
    _event(session, principal, request_id, "shelter.registered", "shelter", shelter.id)
    return shelter_out(shelter)


def update_shelter(session, principal, shelter_id, data, request_id):
    shelter = shelter_or_404(session, principal, shelter_id)
    payload = data.model_dump(exclude_unset=True)
    if "block_id" in payload:
        shelter.block_id = block_in_tenant(session, principal, parse_uuid(payload["block_id"], "block_id")).id
    if "warden_user_id" in payload:
        warden = user_in_tenant(session, principal, parse_uuid(payload["warden_user_id"], "warden_user_id"))
        if warden.role != "warden":
            raise ApiError(404, "NOT_FOUND")
        shelter.warden_user_id = warden.id
    for field in ("name", "location_label", "latitude", "longitude", "capacity", "reporting_contact", "operational_status"):
        if field in payload:
            setattr(shelter, field, payload[field])
    _event(session, principal, request_id, "shelter.updated", "shelter", shelter.id, {"fields": list(payload)})
    return shelter_out(shelter)


def create_user(session, principal, data, request_id):
    if session.query(User).filter(User.username == data.username).first():
        raise ApiError(409, "DUPLICATE_MISMATCH")
    shelter_id = parse_uuid(data.shelter_id, "shelter_id") if data.shelter_id else None
    block_id = parse_uuid(data.block_id, "block_id") if data.block_id else None
    if shelter_id:
        shelter_or_404(session, principal, shelter_id)
    if block_id:
        block_in_tenant(session, principal, block_id)
    user = User(
        tenant_id=principal.tenant_id,
        name=data.name,
        username=data.username,
        role=data.role,
        organization=data.organization,
        status="active",
        password_hash=hash_password(data.password),
        grants=list(data.grants),
    )
    session.add(user)
    session.flush()
    assignment = Assignment(
        tenant_id=principal.tenant_id,
        user_id=user.id,
        shelter_id=shelter_id,
        block_id=block_id,
        support_functions=list(data.support_functions),
    )
    session.add(assignment)
    _event(session, principal, request_id, "user.registered", "user", user.id)
    return user_out(user, assignment)


def update_user(session, principal, user_id, data, request_id):
    user = user_in_tenant(session, principal, user_id)
    assignment = session.query(Assignment).filter(Assignment.user_id == user.id).one_or_none()
    changed_assignment = False
    payload = data.model_dump(exclude_unset=True)
    for field in ("name", "organization", "status", "role"):
        if field in payload and payload[field] is not None:
            setattr(user, field, payload[field])
    if "grants" in payload and payload["grants"] is not None:
        user.grants = list(payload["grants"])
    if assignment is None:
        assignment = Assignment(tenant_id=user.tenant_id, user_id=user.id, support_functions=[])
        session.add(assignment)
    if "shelter_id" in payload:
        assignment.shelter_id = parse_uuid(payload["shelter_id"], "shelter_id") if payload["shelter_id"] else None
        changed_assignment = True
    if "block_id" in payload:
        assignment.block_id = parse_uuid(payload["block_id"], "block_id") if payload["block_id"] else None
        changed_assignment = True
    if "support_functions" in payload and payload["support_functions"] is not None:
        assignment.support_functions = list(payload["support_functions"])
        changed_assignment = True
    if "role" in payload:
        changed_assignment = True
    event_type = "user.assignment_changed" if changed_assignment else "user.registered"
    if changed_assignment or "status" in payload:
        _event(session, principal, request_id, "user.assignment_changed" if changed_assignment else event_type, "user", user.id)
    if user.status == "inactive":
        from modules.persistence.tables import RefreshToken

        session.query(RefreshToken).filter(RefreshToken.user_id == user.id).update({"revoked": True})
    return user_out(user, assignment)


def create_tenant(session, principal, data, request_id):
    if session.query(Tenant).filter(Tenant.code == data.code).first():
        raise ApiError(409, "DUPLICATE_MISMATCH")
    tenant = Tenant(name=data.name, code=data.code, status="active")
    session.add(tenant)
    session.flush()
    publish(
        session,
        event_type="tenant.created",
        tenant_id=tenant.id,
        actor_id=principal.user_id,
        aggregate_type="tenant",
        aggregate_id=tenant.id,
        payload={"name": tenant.name},
        request_id=request_id,
    )
    return {"id": str(tenant.id), "name": tenant.name, "code": tenant.code, "status": tenant.status}


def create_block(session, principal, tenant_id, data, request_id):
    if tenant_id != principal.tenant_id and not principal.allows("tenant.manage"):
        raise ApiError(404, "NOT_FOUND")
    if session.query(Block).filter(Block.tenant_id == tenant_id, Block.code == data.code).first():
        raise ApiError(409, "DUPLICATE_MISMATCH")
    block = Block(tenant_id=tenant_id, name=data.name, code=data.code)
    session.add(block)
    session.flush()
    return {"id": str(block.id), "name": block.name, "code": block.code, "tenant_id": str(block.tenant_id)}


def save_configuration(session, principal, tenant_id, data):
    if tenant_id != principal.tenant_id and not principal.allows("tenant.manage"):
        raise ApiError(404, "NOT_FOUND")
    row = session.get(TenantConfiguration, tenant_id)
    if row is None:
        row = TenantConfiguration(tenant_id=tenant_id)
        session.add(row)
    dumped = data.model_dump()
    row.shortage = dumped["shortage"]
    row.capacity = dumped["capacity"]
    row.priority = dumped["priority"]
    return dumped


def get_configuration(session, principal, tenant_id):
    if tenant_id != principal.tenant_id and not principal.allows("tenant.manage"):
        raise ApiError(404, "NOT_FOUND")
    row = session.get(TenantConfiguration, tenant_id)
    if row is None:
        return {"shortage": None, "capacity": None, "priority": None}
    return {"shortage": row.shortage, "capacity": row.capacity, "priority": row.priority}


def transition_alert(session, principal, alert_id, name, note, request_id):
    source, target, event_type = TRANSITIONS[name]
    alert = session.get(Alert, alert_id)
    if alert is None or alert.tenant_id != principal.tenant_id:
        raise ApiError(404, "NOT_FOUND")
    shelter_or_404(session, principal, alert.shelter_id)
    if alert.status != source:
        raise ApiError(422, "INVALID_STATE")
    alert.status = target
    alert.updated_at = utcnow()
    _event(session, principal, request_id, event_type, "alert", alert.id, {"note": note})
    return alert_out(alert)


def _action_or_404(session, principal, action_id) -> ActionRecord:
    action = session.get(ActionRecord, action_id)
    if action is None or action.tenant_id != principal.tenant_id:
        raise ApiError(404, "NOT_FOUND")
    destination = session.get(Shelter, action.destination_shelter_id)
    source = session.get(Shelter, action.source_shelter_id)
    if principal.role == "district_officer":
        return action
    if principal.role == "block_officer" and (
        (destination and destination.block_id == principal.block_id) or (source and source.block_id == principal.block_id)
    ):
        return action
    if principal.shelter_id in {action.source_shelter_id, action.destination_shelter_id}:
        return action
    raise ApiError(404, "NOT_FOUND")


def decide_action(session, principal, action_id, decision, note, quantity, request_id):
    action = _action_or_404(session, principal, action_id)
    if action.decision != "proposed":
        raise ApiError(422, "INVALID_STATE")
    action.decision = decision
    action.status = decision
    action.decided_by = principal.user_id
    action.decided_at = utcnow()
    action.decision_note = note
    if decision == "modified":
        action.approved_quantity = quantity
    elif decision == "approved":
        action.approved_quantity = action.suggested_quantity
    event_type = {"approved": "action.approved", "modified": "action.modified", "rejected": "action.rejected"}[decision]
    _event(session, principal, request_id, event_type, "action", action.id)
    return action_out(action)


def confirm_receipt(session, principal, action_id, quantity, unit, request_id):
    action = _action_or_404(session, principal, action_id)
    if action.decision not in {"approved", "modified"}:
        raise ApiError(422, "HUMAN_APPROVAL_REQUIRED")
    if principal.shelter_id != action.destination_shelter_id:
        raise ApiError(404, "NOT_FOUND")
    action.received_quantity = quantity
    action.receipt_confirmed_at = utcnow()
    action.status = "receipt_confirmed"
    _event(session, principal, request_id, "action.receipt_confirmed", "action", action.id, {"quantity": quantity, "unit": unit})
    return action_out(action)


def create_sync_batch(session, principal, data, request_id):
    batch = SyncBatch(tenant_id=principal.tenant_id, actor_id=principal.user_id, created_at=utcnow())
    session.add(batch)
    session.flush()
    for report in data.reports:
        session.add(
            SyncItem(
                batch_id=batch.id,
                tenant_id=principal.tenant_id,
                client_report_id=parse_uuid(report.client_report_id, "client_report_id"),
                state="queued",
                body=report.model_dump(mode="json"),
            )
        )
    _event(session, principal, request_id, "sync.batch_accepted", "sync_batch", batch.id)
    return {"batch_id": str(batch.id), "accepted_count": len(data.reports)}
