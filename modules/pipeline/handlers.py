import uuid

from common.events.bus import publish
from common.timeutil import utcnow
from modules.persistence.tables import (
    ActionRecord,
    Alert,
    ResourceHistory,
    ResourceSnapshot,
    Shelter,
    ShelterReport,
    TenantConfiguration,
)
from modules.pipeline.evaluate import CLEARABLE, OPEN_ALERT, RANK, capacity_severity, shortage_severity

FIELDS = (
    ("food", "food_quantity", "food_unit"),
    ("water", "water_quantity", "water_unit"),
    ("medicine", "medicine_quantity", "medicine_unit"),
)


def register(subscribe) -> None:
    subscribe("report.submitted", on_report_submitted)
    subscribe("report.stored_historical", on_report_stored_historical)
    subscribe("resource.snapshot_updated", on_snapshot_updated)
    subscribe("shortage.condition_met", on_shortage)
    subscribe("capacity.condition_met", on_capacity)
    subscribe("sync.batch_accepted", on_sync_batch)
    subscribe("shelter.updated", on_shelter_updated)


def _ids(envelope):
    return uuid.UUID(envelope["tenant_id"]), uuid.UUID(envelope["aggregate_id"]), envelope


def _emit(session, envelope, event_type, aggregate_type, aggregate_id, payload):
    publish(
        session,
        event_type=event_type,
        tenant_id=uuid.UUID(envelope["tenant_id"]),
        actor_id=None,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload={"cause_event_id": envelope["event_id"], **payload},
        request_id=envelope.get("request_id"),
    )


def _history(session, report, applied_snapshot: bool) -> None:
    for kind, qty_attr, unit_attr in FIELDS:
        session.add(
            ResourceHistory(
                tenant_id=report.tenant_id,
                shelter_id=report.shelter_id,
                report_id=report.id,
                resource_type=kind,
                quantity=getattr(report, qty_attr),
                unit=getattr(report, unit_attr),
                recorded_at=report.reported_at,
            )
        )
        if not applied_snapshot:
            continue
        current = (
            session.query(ResourceSnapshot)
            .filter(
                ResourceSnapshot.tenant_id == report.tenant_id,
                ResourceSnapshot.shelter_id == report.shelter_id,
                ResourceSnapshot.resource_type == kind,
            )
            .one_or_none()
        )
        if current is None:
            session.add(
                ResourceSnapshot(
                    tenant_id=report.tenant_id,
                    shelter_id=report.shelter_id,
                    report_id=report.id,
                    resource_type=kind,
                    quantity=getattr(report, qty_attr),
                    unit=getattr(report, unit_attr),
                    recorded_at=report.reported_at,
                )
            )
        else:
            current.report_id = report.id
            current.quantity = getattr(report, qty_attr)
            current.unit = getattr(report, unit_attr)
            current.recorded_at = report.reported_at


def on_report_submitted(session, envelope) -> None:
    _, report_id, _ = _ids(envelope)
    report = session.get(ShelterReport, report_id)
    _history(session, report, True)
    _emit(session, envelope, "resource.snapshot_updated", "shelter", report.shelter_id, {"report_id": str(report.id)})


def on_report_stored_historical(session, envelope) -> None:
    _, report_id, _ = _ids(envelope)
    report = session.get(ShelterReport, report_id)
    _history(session, report, False)


def on_snapshot_updated(session, envelope) -> None:
    tenant_id, shelter_id, _ = _ids(envelope)
    shelter = session.get(Shelter, shelter_id)
    config = session.get(TenantConfiguration, tenant_id)
    shortage = config.shortage if config else None
    capacity = config.capacity if config else None
    snapshots = session.query(ResourceSnapshot).filter(ResourceSnapshot.shelter_id == shelter.id).all()
    severities = []
    shortage_events = []
    if not shortage:
        _emit(session, envelope, "shortage.evaluation_skipped", "shelter", shelter.id, {})
    else:
        for snap in snapshots:
            severity = shortage_severity(snap.quantity, shortage[snap.resource_type])
            if severity:
                severities.append(severity)
            shortage_events.append((snap, severity))
    capacity_event = None
    if not capacity or shelter.current_population is None:
        _emit(session, envelope, "capacity.evaluation_skipped", "shelter", shelter.id, {})
    else:
        severity = capacity_severity(shelter.current_population, shelter.capacity, capacity)
        if severity:
            severities.append(severity)
        capacity_event = severity
    if shortage and capacity:
        if "urgent" in severities:
            shelter.current_status = "red"
        elif "attention" in severities:
            shelter.current_status = "yellow"
        else:
            shelter.current_status = "green"
    else:
        shelter.current_status = "unknown"
    _emit(session, envelope, "shelter.status_recalculated", "shelter", shelter.id, {"current_status": shelter.current_status})
    if shortage:
        for snap, severity in shortage_events:
            _apply_condition(
                session,
                envelope,
                shelter,
                "shortage",
                snap.resource_type,
                severity,
                "shortage.condition_met",
                {"quantity": snap.quantity, "unit": snap.unit},
            )
    if capacity and shelter.current_population is not None:
        _apply_condition(
            session,
            envelope,
            shelter,
            "capacity",
            None,
            capacity_event,
            "capacity.condition_met",
            {"population": shelter.current_population, "capacity": shelter.capacity},
        )


def _open_alert(session, shelter, alert_type, resource_type):
    query = session.query(Alert).filter(
        Alert.tenant_id == shelter.tenant_id,
        Alert.shelter_id == shelter.id,
        Alert.type == alert_type,
        Alert.status.in_(tuple(OPEN_ALERT)),
    )
    if resource_type is None:
        query = query.filter(Alert.resource_type.is_(None))
    else:
        query = query.filter(Alert.resource_type == resource_type)
    return query.order_by(Alert.created_at.desc()).first()


def _apply_condition(session, envelope, shelter, alert_type, resource_type, severity, event_name, extra) -> None:
    active = _open_alert(session, shelter, alert_type, resource_type)
    if severity is None:
        if active and active.status in CLEARABLE:
            active.status = "resolved"
            active.updated_at = utcnow()
            _emit(session, envelope, "alert.auto_cleared", "alert", active.id, {})
        return
    if active is None:
        alert = Alert(
            tenant_id=shelter.tenant_id,
            shelter_id=shelter.id,
            type=alert_type,
            resource_type=resource_type,
            severity=severity,
            status="detected",
            created_at=utcnow(),
            updated_at=utcnow(),
            cause_event_id=uuid.UUID(envelope["event_id"]),
        )
        session.add(alert)
        session.flush()
        _emit(session, envelope, event_name, "alert", alert.id, {"severity": severity, "resource_type": resource_type, **extra})
        _emit(session, envelope, "alert.detected", "alert", alert.id, {"grouped": False, "severity": severity, "type": alert_type, "resource_type": resource_type})
        return
    if RANK[severity] > RANK[active.severity]:
        active.severity = severity
        active.updated_at = utcnow()
        _emit(session, envelope, "alert.detected", "alert", active.id, {"grouped": True, "severity": severity, "type": alert_type, "resource_type": resource_type})
    elif RANK[severity] < RANK[active.severity]:
        active.severity = severity
        active.updated_at = utcnow()
        _emit(session, envelope, "alert.downgraded", "alert", active.id, {"severity": severity})


def on_shortage(session, envelope) -> None:
    tenant_id = uuid.UUID(envelope["tenant_id"])
    alert = session.get(Alert, uuid.UUID(envelope["aggregate_id"]))
    if alert is None:
        return
    config = session.get(TenantConfiguration, tenant_id)
    if config is None or not config.shortage:
        return
    resource_type = envelope["payload"].get("resource_type") or alert.resource_type
    rule = config.shortage[resource_type]
    destination = session.get(Shelter, alert.shelter_id)
    snapshots = (
        session.query(ResourceSnapshot)
        .filter(ResourceSnapshot.tenant_id == tenant_id, ResourceSnapshot.resource_type == resource_type, ResourceSnapshot.quantity > rule["surplus_above"])
        .all()
    )
    sources = []
    for snap in snapshots:
        if snap.shelter_id == destination.id:
            continue
        source = session.get(Shelter, snap.shelter_id)
        if source is not None and source.tenant_id == tenant_id:
            sources.append((source, snap))
    sources.sort(key=lambda pair: (0 if pair[0].block_id == destination.block_id else 1, pair[0].name))
    for source, snap in sources:
        exists = (
            session.query(ActionRecord)
            .filter(ActionRecord.alert_id == alert.id, ActionRecord.source_shelter_id == source.id)
            .first()
        )
        if exists:
            continue
        action = ActionRecord(
            tenant_id=tenant_id,
            alert_id=alert.id,
            source_shelter_id=source.id,
            destination_shelter_id=destination.id,
            resource_type=resource_type,
            suggested_quantity=snap.quantity,
            decision="proposed",
            status="proposed",
            explanation_key="action.explanation",
            explanation_params={
                "source_shelter_name": source.name,
                "resource_type": resource_type,
                "quantity": snap.quantity,
                "unit": snap.unit,
            },
        )
        session.add(action)
        session.flush()
        _emit(session, envelope, "action.proposed", "action", action.id, {"alert_id": str(alert.id)})


def on_capacity(session, envelope) -> None:
    return None


def on_shelter_updated(session, envelope) -> None:
    shelter_id = uuid.UUID(envelope["aggregate_id"])
    _emit(session, envelope, "resource.snapshot_updated", "shelter", shelter_id, {})


def on_sync_batch(session, envelope) -> None:
    from modules.persistence.tables import SyncItem
    from modules.schemas.bodies import ReportCreate
    from modules.services.report_service import submit
    from common.api.errors import ApiError
    from common.authz.principal import Principal, permissions_for
    from modules.persistence.tables import Assignment, User

    batch_id = uuid.UUID(envelope["aggregate_id"])
    actor = session.get(User, uuid.UUID(envelope["actor_id"])) if envelope.get("actor_id") else None
    items = session.query(SyncItem).filter(SyncItem.batch_id == batch_id).all()
    if actor is None:
        return
    assignment = session.query(Assignment).filter(Assignment.user_id == actor.id).one_or_none()
    support = list(assignment.support_functions or []) if assignment else []
    principal = Principal(
        user_id=actor.id,
        tenant_id=actor.tenant_id,
        role=actor.role,
        shelter_id=assignment.shelter_id if assignment else None,
        block_id=assignment.block_id if assignment else None,
        permissions=permissions_for(actor.role, support, list(actor.grants or [])),
        support_functions=support,
    )
    for item in items:
        try:
            data = ReportCreate.model_validate(item.body)
            result = submit(session, principal, data, envelope.get("request_id") or "")
            if result["meta"] and result["meta"].get("idempotent_replay"):
                item.state = "duplicate"
            elif result["data"]["applied_to_current"]:
                item.state = "applied"
            else:
                item.state = "stored_historical"
            item.error_code = None
        except ApiError as exc:
            item.state = "rejected"
            item.error_code = exc.code
