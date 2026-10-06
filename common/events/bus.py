import uuid

from common.persistence import ensure_models
from common.timeutil import utcnow

ensure_models()

HANDLERS: dict[str, list] = {}
_registered = False


def subscribe(event_type: str, handler) -> None:
    HANDLERS.setdefault(event_type, []).append(handler)


def publish(session, *, event_type: str, tenant_id, actor_id, aggregate_type: str, aggregate_id, payload: dict, request_id: str | None):
    from modules.persistence.tables import Outbox

    event_id = uuid.uuid4()
    session.add(
        Outbox(
            event_id=event_id,
            tenant_id=tenant_id,
            event_type=event_type,
            actor_id=actor_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            request_id=request_id,
            payload=payload,
            created_at=utcnow(),
        )
    )
    return event_id


def register_handlers() -> None:
    global _registered
    if _registered:
        return
    from modules.pipeline.handlers import register

    register(subscribe)
    _registered = True


def drain(session, loops: int = 15) -> None:
    from modules.persistence.tables import Outbox, ProcessedEvent

    register_handlers()
    session.commit()
    for _ in range(loops):
        rows = (
            session.query(Outbox)
            .filter(Outbox.published_at.is_(None))
            .order_by(Outbox.created_at)
            .all()
        )
        if not rows:
            return
        for row in list(rows):
            event_id = row.event_id
            try:
                if session.get(ProcessedEvent, event_id) is None:
                    envelope = _envelope(row)
                    for handler in HANDLERS.get(row.event_type, []):
                        handler(session, envelope)
                    session.add(_audit(envelope))
                    session.add(ProcessedEvent(event_id=event_id))
                row.published_at = utcnow()
                row.last_error = None
                session.commit()
            except Exception as exc:
                session.rollback()
                fresh = session.get(Outbox, event_id)
                if fresh is not None:
                    fresh.attempts += 1
                    fresh.last_error = str(exc)[:500]
                    session.commit()
                return


def _envelope(row) -> dict:
    return {
        "event_id": str(row.event_id),
        "event_type": row.event_type,
        "occurred_at": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tenant_id": str(row.tenant_id),
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "request_id": row.request_id,
        "aggregate_type": row.aggregate_type,
        "aggregate_id": str(row.aggregate_id),
        "payload": row.payload or {},
    }


def _audit(envelope: dict) -> "AuditEvent":
    from modules.persistence.tables import AuditEvent

    payload = dict(envelope["payload"])
    if envelope["event_type"] in {"shortage.evaluation_skipped", "capacity.evaluation_skipped"}:
        payload["technical_skip"] = True
    return AuditEvent(
        tenant_id=uuid.UUID(envelope["tenant_id"]),
        event_id=uuid.UUID(envelope["event_id"]),
        event_type=envelope["event_type"],
        actor_id=uuid.UUID(envelope["actor_id"]) if envelope["actor_id"] else None,
        aggregate_type=envelope["aggregate_type"],
        aggregate_id=uuid.UUID(envelope["aggregate_id"]),
        occurred_at=utcnow(),
        request_id=envelope["request_id"],
        payload=payload,
    )
