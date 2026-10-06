import hashlib
import json
import uuid
from datetime import datetime

from common.api.errors import ApiError
from common.events.bus import publish
from common.timeutil import as_utc, isoformat, utcnow
from modules.persistence.tables import AuditEvent, Outbox, Shelter, ShelterReport
from modules.presenters import report_out
from modules.services.scope import parse_uuid, shelter_or_404


def _reported_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ApiError(400, "VALIDATION_ERROR", details=[{"field": "reported_at", "code": "INVALID"}])
    return parsed


def canonical_hash(data) -> str:
    vulnerability = data.vulnerability
    body = {
        "channel": data.channel,
        "incident_notes": data.incident_notes or "",
        "population": data.population,
        "reported_at": isoformat(_reported_at(data.reported_at)),
        "resources": sorted(
            [{"resource_type": item.resource_type, "quantity": item.quantity, "unit": item.unit} for item in data.resources],
            key=lambda item: item["resource_type"],
        ),
        "shelter_id": str(parse_uuid(data.shelter_id, "shelter_id")),
        "vulnerability": {
            "children": vulnerability.children,
            "injured_or_sick": vulnerability.injured_or_sick,
            "older_adults": vulnerability.older_adults,
            "persons_with_disability": vulnerability.persons_with_disability,
            "pregnant_women": vulnerability.pregnant_women,
        },
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def _resource(data, kind: str):
    for item in data.resources:
        if item.resource_type == kind:
            return item
    raise ApiError(400, "VALIDATION_ERROR", details=[{"field": "resources", "code": "RESOURCE_SET"}])


def submit(session, principal, data, request_id: str, *, channel: str | None = None):
    shelter_id = parse_uuid(data.shelter_id, "shelter_id")
    client_id = parse_uuid(data.client_report_id, "client_report_id")
    shelter = shelter_or_404(session, principal, shelter_id)
    if principal.role == "warden" and shelter.id != principal.shelter_id:
        raise ApiError(404, "NOT_FOUND")
    if principal.role == "volunteer" and "reporting_support" not in principal.support_functions:
        raise ApiError(403, "PERMISSION_DENIED")
    digest = canonical_hash(data)
    existing = (
        session.query(ShelterReport)
        .filter(ShelterReport.tenant_id == principal.tenant_id, ShelterReport.client_report_id == client_id)
        .one_or_none()
    )
    if existing is not None:
        if existing.payload_hash != digest:
            raise ApiError(409, "DUPLICATE_MISMATCH")
        _mark_duplicate_once(session, principal, existing, request_id)
        return {"status": 200, "data": report_out(existing), "meta": {"idempotent_replay": True}}
    reported_at = _reported_at(data.reported_at)
    last_applied = as_utc(shelter.last_applied_report_at) if shelter.last_applied_report_at else None
    applied = last_applied is None or reported_at >= last_applied
    food, water, medicine = _resource(data, "food"), _resource(data, "water"), _resource(data, "medicine")
    report = ShelterReport(
        client_report_id=client_id,
        tenant_id=principal.tenant_id,
        shelter_id=shelter.id,
        reported_at=reported_at,
        received_at=utcnow(),
        population=data.population,
        children=data.vulnerability.children,
        older_adults=data.vulnerability.older_adults,
        pregnant_women=data.vulnerability.pregnant_women,
        persons_with_disability=data.vulnerability.persons_with_disability,
        injured_or_sick=data.vulnerability.injured_or_sick,
        food_quantity=food.quantity,
        food_unit=food.unit,
        water_quantity=water.quantity,
        water_unit=water.unit,
        medicine_quantity=medicine.quantity,
        medicine_unit=medicine.unit,
        incident_notes=data.incident_notes,
        channel=channel or data.channel,
        applied_to_current=applied,
        actor_id=principal.user_id,
        payload_hash=digest,
    )
    session.add(report)
    session.flush()
    if applied:
        shelter.last_applied_report_at = reported_at
        shelter.current_population = data.population
        event_type = "report.submitted"
    else:
        event_type = "report.stored_historical"
    publish(
        session,
        event_type=event_type,
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        aggregate_type="shelter_report",
        aggregate_id=report.id,
        payload={"shelter_id": str(shelter.id)},
        request_id=request_id,
    )
    return {"status": 201, "data": report_out(report), "meta": None}


def _mark_duplicate_once(session, principal, report, request_id: str) -> None:
    already = (
        session.query(Outbox)
        .filter(Outbox.aggregate_id == report.id, Outbox.event_type == "report.duplicate_ignored")
        .first()
    )
    audited = (
        session.query(AuditEvent)
        .filter(AuditEvent.aggregate_id == report.id, AuditEvent.event_type == "report.duplicate_ignored")
        .first()
    )
    if already or audited:
        return
    publish(
        session,
        event_type="report.duplicate_ignored",
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        aggregate_type="shelter_report",
        aggregate_id=report.id,
        payload={"client_report_id": str(report.client_report_id)},
        request_id=request_id,
    )


def submit_from_channel(session, tenant_id, shelter: Shelter, normalized: dict, request_id: str):
    from types import SimpleNamespace

    class _System:
        role = "district_officer"
        tenant_id = tenant_id
        user_id = None
        shelter_id = None
        block_id = None
        support_functions: list[str] = []

        def allows(self, _permission: str) -> bool:
            return True

    data = SimpleNamespace(**normalized)
    data.vulnerability = SimpleNamespace(**normalized["vulnerability"])
    data.resources = [SimpleNamespace(**item) for item in normalized["resources"]]
    principal = _System()
    principal.tenant_id = shelter.tenant_id
    data.channel = normalized["channel"]
    return submit(session, principal, data, request_id, channel=normalized["channel"])
