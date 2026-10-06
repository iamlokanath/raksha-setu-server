from datetime import datetime

from common.api.errors import ApiError
from common.timeutil import as_utc, isoformat, utcnow
from modules.persistence.tables import (
    ActionRecord,
    Alert,
    AuditEvent,
    Block,
    ResourceSnapshot,
    ShelterReport,
    SyncBatch,
    SyncItem,
    Tenant,
    TenantConfiguration,
)
from modules.pipeline.evaluate import occupancy_band, priority_band, priority_score
from modules.presenters import action_out, alert_out, report_out, resources_of, shelter_out, vulnerability_of
from modules.services.scope import block_in_tenant, paginate, parse_uuid, scoped_shelters, shelter_or_404

SECRET_KEYS = {"password", "password_hash", "access_token", "refresh_token", "token"}
STATUS_ORDER = {"red": 0, "yellow": 1, "green": 2, "unknown": 3}
OPEN_ALERTS = ("detected", "acknowledged", "action_planned", "action_in_progress")


def _parse_time(value: str | None, field: str):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, "VALIDATION_ERROR", details=[{"field": field, "code": "INVALID"}])
    return as_utc(parsed)


def list_shelters(session, principal, query):
    statement = scoped_shelters(session, principal)
    if query.operational_status:
        statement = statement.filter_by(operational_status=query.operational_status)
    if query.block_id:
        block_id = parse_uuid(query.block_id, "block_id")
        if principal.role == "block_officer" and block_id != principal.block_id:
            raise ApiError(403, "PERMISSION_DENIED")
        block_in_tenant(session, principal, block_id)
        statement = statement.filter_by(block_id=block_id)
    from modules.persistence.tables import Shelter

    sort_column = Shelter.name if query.sort == "name" else Shelter.current_status
    rows, meta = paginate(statement.order_by(sort_column), query.page, query.page_size)
    return [shelter_out(row) for row in rows], meta


def list_reports(session, principal, query, shelter_id=None):
    from modules.persistence.tables import ShelterReport as Report

    if shelter_id is not None:
        shelter_or_404(session, principal, shelter_id)
        statement = session.query(Report).filter(Report.shelter_id == shelter_id, Report.tenant_id == principal.tenant_id)
    else:
        visible = [row.id for row in scoped_shelters(session, principal).all()]
        statement = session.query(Report).filter(Report.tenant_id == principal.tenant_id, Report.shelter_id.in_(visible or [None]))
        if query.shelter_id:
            shelter = shelter_or_404(session, principal, parse_uuid(query.shelter_id, "shelter_id"))
            statement = statement.filter(Report.shelter_id == shelter.id)
    if query.channel:
        statement = statement.filter(Report.channel == query.channel)
    start = _parse_time(query.from_time, "from")
    end = _parse_time(query.to_time, "to")
    if start:
        statement = statement.filter(Report.reported_at >= start)
    if end:
        statement = statement.filter(Report.reported_at <= end)
    rows, meta = paginate(statement.order_by(Report.reported_at.desc()), query.page, query.page_size)
    return [report_out(row) for row in rows], meta


def shelter_resources(session, principal, shelter_id):
    shelter = shelter_or_404(session, principal, shelter_id)
    snaps = {
        row.resource_type: row
        for row in session.query(ResourceSnapshot).filter(ResourceSnapshot.shelter_id == shelter.id).all()
    }
    data = []
    for kind in ("food", "water", "medicine"):
        snap = snaps.get(kind)
        if snap is None:
            data.append({"resource_type": kind, "quantity": None, "unit": None, "status": "unreported"})
        else:
            data.append({"resource_type": kind, "quantity": snap.quantity, "unit": snap.unit, "status": "reported", "recorded_at": isoformat(snap.recorded_at)})
    return data


def list_resources(session, principal, query):
    config = session.get(TenantConfiguration, principal.tenant_id)
    if query.surplus is True and (config is None or not config.shortage):
        raise ApiError(422, "CONFIGURATION_REQUIRED")
    shelters = {row.id: row for row in scoped_shelters(session, principal).all()}
    if query.block_id:
        block_id = parse_uuid(query.block_id, "block_id")
        if principal.role == "block_officer" and block_id != principal.block_id:
            raise ApiError(403, "PERMISSION_DENIED")
        shelters = {key: value for key, value in shelters.items() if value.block_id == block_id}
    rows = session.query(ResourceSnapshot).filter(ResourceSnapshot.tenant_id == principal.tenant_id).all()
    items = []
    for row in rows:
        shelter = shelters.get(row.shelter_id)
        if shelter is None:
            continue
        if query.resource_type and row.resource_type != query.resource_type:
            continue
        if query.surplus is True:
            line = config.shortage[row.resource_type]["surplus_above"]
            if not row.quantity > line:
                continue
        if query.surplus is False and config and config.shortage:
            line = config.shortage[row.resource_type]["surplus_above"]
            if row.quantity > line:
                continue
        items.append({"shelter_id": str(row.shelter_id), "resource_type": row.resource_type, "quantity": row.quantity, "unit": row.unit})
    start = (query.page - 1) * query.page_size
    return items[start : start + query.page_size], {"page": query.page, "page_size": query.page_size, "total": len(items)}


def list_alerts(session, principal, query):
    visible = {row.id: row for row in scoped_shelters(session, principal).all()}
    statement = session.query(Alert).filter(Alert.tenant_id == principal.tenant_id, Alert.shelter_id.in_(list(visible) or [None]))
    if query.status:
        statement = statement.filter(Alert.status == query.status)
    if query.severity:
        statement = statement.filter(Alert.severity == query.severity)
    if query.type:
        statement = statement.filter(Alert.type == query.type)
    if query.shelter_id:
        shelter_or_404(session, principal, parse_uuid(query.shelter_id, "shelter_id"))
        statement = statement.filter(Alert.shelter_id == parse_uuid(query.shelter_id, "shelter_id"))
    if query.block_id:
        block_id = parse_uuid(query.block_id, "block_id")
        if principal.role == "block_officer" and block_id != principal.block_id:
            raise ApiError(403, "PERMISSION_DENIED")
        ids = [key for key, value in visible.items() if value.block_id == block_id]
        statement = statement.filter(Alert.shelter_id.in_(ids or [None]))
    order = Alert.severity if query.sort == "severity" else Alert.created_at.desc()
    rows, meta = paginate(statement.order_by(order), query.page, query.page_size)
    return [alert_out(row) for row in rows], meta


def get_alert(session, principal, alert_id):
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise ApiError(404, "NOT_FOUND")
    shelter_or_404(session, principal, alert.shelter_id)
    return alert_out(alert)


def list_actions(session, principal, query):
    visible = {row.id: row for row in scoped_shelters(session, principal).all()}
    rows = session.query(ActionRecord).filter(ActionRecord.tenant_id == principal.tenant_id).all()
    items = []
    for action in rows:
        if action.source_shelter_id not in visible and action.destination_shelter_id not in visible:
            continue
        if query.decision and action.decision != query.decision:
            continue
        if query.shelter_id:
            shelter_id = parse_uuid(query.shelter_id, "shelter_id")
            if shelter_id not in {action.source_shelter_id, action.destination_shelter_id}:
                continue
        if query.block_id:
            block_id = parse_uuid(query.block_id, "block_id")
            if principal.role == "block_officer" and block_id != principal.block_id:
                raise ApiError(403, "PERMISSION_DENIED")
            source = visible.get(action.source_shelter_id)
            destination = visible.get(action.destination_shelter_id)
            if not ((source and source.block_id == block_id) or (destination and destination.block_id == block_id)):
                continue
        items.append(action_out(action))
    start = (query.page - 1) * query.page_size
    return items[start : start + query.page_size], {"page": query.page, "page_size": query.page_size, "total": len(items)}


def get_action(session, principal, action_id):
    from modules.services.records import _action_or_404

    return action_out(_action_or_404(session, principal, action_id))


def _latest_applied(session, shelter_id):
    return (
        session.query(ShelterReport)
        .filter(ShelterReport.shelter_id == shelter_id, ShelterReport.applied_to_current.is_(True))
        .order_by(ShelterReport.reported_at.desc())
        .first()
    )


def _factors(session, shelter):
    report = _latest_applied(session, shelter.id)
    vulnerable = 0
    if report:
        vulnerable = sum(vulnerability_of(report).values())
    occupancy = None
    if shelter.current_population is not None and shelter.capacity:
        occupancy = shelter.current_population / shelter.capacity
    alerts = session.query(Alert).filter(Alert.shelter_id == shelter.id, Alert.status.in_(OPEN_ALERTS)).all()
    urgency = "none"
    if any(alert.type == "shortage" and alert.severity == "urgent" for alert in alerts):
        urgency = "urgent"
    elif any(alert.type == "shortage" and alert.severity == "attention" for alert in alerts):
        urgency = "attention"
    if alerts:
        oldest = min(as_utc(alert.created_at) for alert in alerts)
        age = max((utcnow() - oldest).total_seconds(), 0)
    elif report:
        age = max((utcnow() - as_utc(report.reported_at)).total_seconds(), 0)
    else:
        age = 0
    return {
        "shortage_urgency": urgency,
        "vulnerable_population": vulnerable,
        "occupancy_pressure": occupancy,
        "issue_age_seconds": int(age),
    }


def _dashboard_rows(session, principal, block_id=None):
    config = session.get(TenantConfiguration, principal.tenant_id)
    shelters = scoped_shelters(session, principal).all()
    if block_id is not None:
        shelters = [shelter for shelter in shelters if shelter.block_id == block_id]
    rows = []
    for shelter in shelters:
        factors = _factors(session, shelter)
        score = priority_score(factors, config.priority if config else None)
        report = _latest_applied(session, shelter.id)
        alerts = session.query(Alert).filter(Alert.shelter_id == shelter.id, Alert.status.in_(OPEN_ALERTS)).all()
        actions = (
            session.query(ActionRecord)
            .filter(ActionRecord.destination_shelter_id == shelter.id, ActionRecord.decision == "proposed")
            .all()
        )
        snaps = {snap.resource_type: snap for snap in session.query(ResourceSnapshot).filter(ResourceSnapshot.shelter_id == shelter.id).all()}
        block = session.get(Block, shelter.block_id)
        rows.append(
            {
                "id": str(shelter.id),
                "name": shelter.name,
                "location_label": shelter.location_label,
                "latitude": shelter.latitude,
                "longitude": shelter.longitude,
                "block_id": str(shelter.block_id),
                "block_name": block.name if block else "",
                "capacity": shelter.capacity,
                "population": shelter.current_population,
                "vulnerability": vulnerability_of(report) if report else None,
                "stocks": [
                    {
                        "resource_type": kind,
                        "quantity": None if kind not in snaps else snaps[kind].quantity,
                        "unit": None if kind not in snaps else snaps[kind].unit,
                    }
                    for kind in ("food", "water", "medicine")
                ],
                "current_status": shelter.current_status,
                "latest_report_at": isoformat(report.reported_at) if report else None,
                "open_alerts": [alert_out(alert) for alert in alerts],
                "proposed_actions": [action_out(action) for action in actions],
                "priority_factors": factors,
                "priority_score": score,
                "occupancy": occupancy_band(shelter.current_population, shelter.capacity, config.capacity if config else None),
            }
        )
    return rows, config


def dashboard_summary(session, principal, block_id=None):
    rows, config = _dashboard_rows(session, principal, block_id)
    surplus = None
    if config and config.shortage:
        surplus = 0
        for row in rows:
            for stock in row["stocks"]:
                if stock["quantity"] is not None and stock["quantity"] > config.shortage[stock["resource_type"]]["surplus_above"]:
                    surplus += 1
                    break
    unresolved = (
        session.query(ActionRecord)
        .filter(ActionRecord.tenant_id == principal.tenant_id)
        .all()
    )
    visible = {row.id for row in scoped_shelters(session, principal).all()}
    unresolved_count = 0
    for action in unresolved:
        if action.destination_shelter_id not in visible and action.source_shelter_id not in visible:
            continue
        if block_id is not None:
            destination = next((row for row in scoped_shelters(session, principal).all() if row.id == action.destination_shelter_id), None)
            if destination is None or destination.block_id != block_id:
                continue
        if action.decision == "proposed" or (action.decision in {"approved", "modified"} and action.receipt_confirmed_at is None):
            unresolved_count += 1
    return {
        "urgent_shelter_count": sum(row["current_status"] == "red" for row in rows),
        "attention_shelter_count": sum(row["current_status"] == "yellow" for row in rows),
        "unknown_shelter_count": sum(row["current_status"] == "unknown" for row in rows),
        "surplus_shelter_count": surplus,
        "unresolved_action_count": unresolved_count,
        "open_alert_count": sum(len(row["open_alerts"]) for row in rows),
    }


def dashboard_shelters(session, principal, query):
    block_id = None
    if principal.role == "block_officer":
        if query.block_id and parse_uuid(query.block_id, "block_id") != principal.block_id:
            raise ApiError(403, "PERMISSION_DENIED")
        block_id = principal.block_id
    elif query.block_id:
        block_id = block_in_tenant(session, principal, parse_uuid(query.block_id, "block_id")).id
    rows, config = _dashboard_rows(session, principal, block_id)
    if query.priority in {"high", "medium", "low"} and (config is None or not config.priority):
        raise ApiError(422, "CONFIGURATION_REQUIRED")
    if query.occupancy in {"below_attention", "attention", "urgent"} and (config is None or not config.capacity):
        raise ApiError(422, "CONFIGURATION_REQUIRED")
    if query.status:
        rows = [row for row in rows if row["current_status"] == query.status]
    if query.shortage_type:
        rows = [row for row in rows if any(alert["type"] == "shortage" and alert["resource_type"] == query.shortage_type for alert in row["open_alerts"])]
    if query.occupancy:
        rows = [row for row in rows if row["occupancy"] == query.occupancy]
    if query.priority:
        rows = [row for row in rows if priority_band(row["priority_score"], config.priority if config else None) == query.priority]
    rows.sort(key=lambda row: (row["priority_score"] is None, -(row["priority_score"] or 0), STATUS_ORDER.get(row["current_status"], 9), row["name"]))
    start = (query.page - 1) * query.page_size
    return rows[start : start + query.page_size], {"page": query.page, "page_size": query.page_size, "total": len(rows)}


def list_users(session, principal, query):
    from modules.persistence.tables import Assignment, User

    statement = session.query(User).filter(User.tenant_id == principal.tenant_id)
    if query.role:
        statement = statement.filter(User.role == query.role)
    users, meta = paginate(statement.order_by(User.name), query.page, query.page_size)
    data = []
    for user in users:
        assignment = session.query(Assignment).filter(Assignment.user_id == user.id).one_or_none()
        if query.block_id and (assignment is None or str(assignment.block_id) != query.block_id):
            continue
        if query.shelter_id and (assignment is None or str(assignment.shelter_id) != query.shelter_id):
            continue
        from modules.presenters import user_out

        data.append(user_out(user, assignment))
    if query.block_id or query.shelter_id:
        meta = {"page": query.page, "page_size": query.page_size, "total": len(data)}
    return data, meta


def list_audit(session, principal, query):
    statement = session.query(AuditEvent).filter(AuditEvent.tenant_id == principal.tenant_id)
    start = _parse_time(query.from_time, "from")
    end = _parse_time(query.to_time, "to")
    if start:
        statement = statement.filter(AuditEvent.occurred_at >= start)
    if end:
        statement = statement.filter(AuditEvent.occurred_at <= end)
    if query.event_type:
        statement = statement.filter(AuditEvent.event_type == query.event_type)
    if query.aggregate_id:
        statement = statement.filter(AuditEvent.aggregate_id == parse_uuid(query.aggregate_id, "aggregate_id"))
    rows, meta = paginate(statement.order_by(AuditEvent.occurred_at.desc()), query.page, query.page_size)
    data = []
    for row in rows:
        payload = {key: value for key, value in (row.payload or {}).items() if key not in SECRET_KEYS}
        data.append(
            {
                "occurred_at": isoformat(row.occurred_at),
                "event_type": row.event_type,
                "actor_id": str(row.actor_id) if row.actor_id else None,
                "aggregate_type": row.aggregate_type,
                "aggregate_id": str(row.aggregate_id),
                "request_id": row.request_id,
                "payload": payload,
            }
        )
    return data, meta


def sync_batch(session, principal, batch_id):
    batch = session.get(SyncBatch, batch_id)
    if batch is None or batch.tenant_id != principal.tenant_id:
        raise ApiError(404, "NOT_FOUND")
    officer = principal.role in {"block_officer", "district_officer"} and principal.allows("report.read")
    if batch.actor_id != principal.user_id and not officer:
        raise ApiError(404, "NOT_FOUND")
    items = session.query(SyncItem).filter(SyncItem.batch_id == batch.id).all()
    return {
        "batch_id": str(batch.id),
        "items": [
            {"client_report_id": str(item.client_report_id), "state": item.state, "error_code": item.error_code}
            for item in items
        ],
    }


def get_tenant(session, principal, tenant_id):
    if tenant_id != principal.tenant_id and not principal.allows("tenant.manage"):
        raise ApiError(404, "NOT_FOUND")
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise ApiError(404, "NOT_FOUND")
    return {"id": str(tenant.id), "name": tenant.name, "code": tenant.code, "status": tenant.status}
