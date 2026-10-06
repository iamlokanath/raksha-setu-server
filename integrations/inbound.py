import uuid

from modules.persistence.tables import Shelter
from modules.services.report_service import submit_from_channel


def provider_report_id(tenant_id, provider: str, message_id: str) -> uuid.UUID:
    return uuid.uuid5(uuid.UUID(str(tenant_id)), f"{provider}:{message_id}")


def ingest(session, tenant_id, address: str, provider: str, message_id: str, observed_at: str, population: int, vulnerability: dict, resources: list, request_id: str):
    shelter = (
        session.query(Shelter)
        .filter(Shelter.tenant_id == tenant_id, Shelter.reporting_contact == address, Shelter.operational_status == "active")
        .one_or_none()
    )
    if shelter is None:
        from common.events.bus import publish

        publish(
            session,
            event_type="integration.ingest_rejected",
            tenant_id=tenant_id,
            actor_id=None,
            aggregate_type="shelter",
            aggregate_id=tenant_id,
            payload={"reason": "unknown_sender", "technical_skip": True},
            request_id=request_id,
        )
        return None
    normalized = {
        "client_report_id": str(provider_report_id(tenant_id, provider, message_id)),
        "shelter_id": str(shelter.id),
        "reported_at": observed_at,
        "population": population,
        "vulnerability": vulnerability,
        "resources": resources,
        "incident_notes": None,
        "channel": "sms" if provider == "sms" else "telephony",
    }
    return submit_from_channel(session, tenant_id, shelter, normalized, request_id)
