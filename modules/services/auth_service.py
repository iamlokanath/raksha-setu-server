import secrets
import uuid
from datetime import timedelta

from common.api.errors import ApiError
from common.authz.passwords import hash_password, hash_token, verify_password
from common.authz.tokens import encode_access_token
from common.events.bus import publish
from common.timeutil import as_utc, utcnow
from django.conf import settings
from modules.persistence.tables import Assignment, RefreshToken, Tenant, User


def _issue_refresh(session, user: User, family_id) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        RefreshToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            family_id=family_id,
            token_hash=hash_token(token),
            revoked=False,
            expires_at=utcnow() + timedelta(seconds=settings.REFRESH_TOKEN_TTL_SECONDS),
            created_at=utcnow(),
        )
    )
    return token


def _pair(session, user: User, family_id) -> dict:
    return {
        "access_token": encode_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role),
        "refresh_token": _issue_refresh(session, user, family_id),
        "token_type": "Bearer",
        "expires_in": settings.ACCESS_TOKEN_TTL_SECONDS,
    }


def login(session, username: str, password: str, request_id: str):
    user = session.query(User).filter(User.username == username).one_or_none()
    if user is None or user.status != "active" or not verify_password(password, user.password_hash):
        if user is not None:
            publish(
                session,
                event_type="auth.login_failed",
                tenant_id=user.tenant_id,
                actor_id=user.id,
                aggregate_type="user",
                aggregate_id=user.id,
                payload={},
                request_id=request_id,
            )
        raise ApiError(401, "AUTH_INVALID")
    pair = _pair(session, user, uuid.uuid4())
    publish(
        session,
        event_type="auth.login_succeeded",
        tenant_id=user.tenant_id,
        actor_id=user.id,
        aggregate_type="user",
        aggregate_id=user.id,
        payload={},
        request_id=request_id,
    )
    return pair


def refresh(session, raw_token: str, request_id: str):
    row = session.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(raw_token)).one_or_none()
    if row is None:
        raise ApiError(401, "AUTH_INVALID")
    if row.revoked:
        session.query(RefreshToken).filter(RefreshToken.family_id == row.family_id).update({"revoked": True})
        raise ApiError(401, "AUTH_INVALID")
    if as_utc(row.expires_at) < utcnow():
        raise ApiError(401, "AUTH_INVALID")
    user = session.get(User, row.user_id)
    if user is None or user.status != "active":
        raise ApiError(401, "AUTH_INVALID")
    row.revoked = True
    return _pair(session, user, row.family_id)


def logout(session, principal, raw_token: str, request_id: str) -> None:
    row = session.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(raw_token)).one_or_none()
    if row is None or row.user_id != principal.user_id:
        raise ApiError(401, "AUTH_INVALID")
    session.query(RefreshToken).filter(RefreshToken.family_id == row.family_id).update({"revoked": True})
    publish(
        session,
        event_type="auth.logout",
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        aggregate_type="user",
        aggregate_id=principal.user_id,
        payload={},
        request_id=request_id,
    )


def me(session, principal) -> dict:
    assignment = session.query(Assignment).filter(Assignment.user_id == principal.user_id).one_or_none()
    user = session.get(User, principal.user_id)
    tenant = session.get(Tenant, user.tenant_id)
    return {
        "id": str(user.id),
        "name": user.name,
        "role": user.role,
        "organization": user.organization,
        "tenant_id": str(user.tenant_id),
        "tenant_name": tenant.name if tenant else "",
        "shelter_id": str(assignment.shelter_id) if assignment and assignment.shelter_id else None,
        "block_id": str(assignment.block_id) if assignment and assignment.block_id else None,
        "permissions": sorted(principal.permissions),
    }
