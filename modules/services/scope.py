import uuid

from common.api.errors import ApiError
from modules.persistence.tables import Block, Shelter, User


def parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError):
        raise ApiError(400, "VALIDATION_ERROR", details=[{"field": field, "code": "INVALID"}])


def require(principal, permission: str) -> None:
    if principal is None:
        raise ApiError(401, "AUTH_INVALID")
    if not principal.allows(permission):
        raise ApiError(403, "PERMISSION_DENIED")


def in_scope(principal, shelter: Shelter) -> bool:
    if shelter.tenant_id != principal.tenant_id:
        return False
    if principal.role == "district_officer":
        return True
    if principal.role == "block_officer":
        return shelter.block_id == principal.block_id
    if principal.role in {"warden", "volunteer"}:
        if principal.shelter_id is not None:
            return shelter.id == principal.shelter_id
        if principal.block_id is not None:
            return shelter.block_id == principal.block_id
    return False


def shelter_or_404(session, principal, shelter_id) -> Shelter:
    shelter = session.get(Shelter, shelter_id)
    if shelter is None or not in_scope(principal, shelter):
        raise ApiError(404, "NOT_FOUND")
    return shelter


def scoped_shelters(session, principal):
    query = session.query(Shelter).filter(Shelter.tenant_id == principal.tenant_id)
    if principal.role == "block_officer":
        query = query.filter(Shelter.block_id == principal.block_id)
    elif principal.role in {"warden", "volunteer"}:
        if principal.shelter_id is not None:
            query = query.filter(Shelter.id == principal.shelter_id)
        elif principal.block_id is not None:
            query = query.filter(Shelter.block_id == principal.block_id)
        else:
            query = query.filter(Shelter.id == None)  # noqa: E711
    return query


def block_in_tenant(session, principal, block_id: uuid.UUID) -> Block:
    block = session.get(Block, block_id)
    if block is None or block.tenant_id != principal.tenant_id:
        raise ApiError(404, "NOT_FOUND")
    return block


def user_in_tenant(session, principal, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if user is None or user.tenant_id != principal.tenant_id:
        raise ApiError(404, "NOT_FOUND")
    return user


def paginate(query, page: int, page_size: int):
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return rows, {"page": page, "page_size": page_size, "total": total}
