import logging
import uuid

import jwt
from django.conf import settings
from django.http import HttpResponse

from common.api.http import error_response
from common.authz.principal import Principal, permissions_for
from common.authz.tokens import decode_access_token
from common.db.session import get_session
from common.events.bus import drain

logger = logging.getLogger("raksha")


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid.uuid4())
        return self.get_response(request)


class CorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            response = HttpResponse(status=204)
            return self._cors(request, response)
        return self._cors(request, self.get_response(request))

    def _cors(self, request, response):
        origin = request.headers.get("Origin")
        if origin and origin in settings.CORS_ALLOWED_ORIGINS:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept, Accept-Language"
            response["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, OPTIONS"
            response["Vary"] = "Origin"
        return response


class DatabaseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.db = get_session()
        try:
            response = self.get_response(request)
            if response.status_code >= 400 and not getattr(request, "persist_side_effects", False):
                request.db.rollback()
            else:
                drain(request.db)
            return response
        except Exception:
            request.db.rollback()
            logger.exception("request_id=%s", request.request_id)
            return error_response(request, 500, "INTERNAL_ERROR")
        finally:
            request.db.close()


class AuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.principal = None
        if request.method == "OPTIONS" or not request.path.startswith("/api/v1/"):
            return self.get_response(request)
        if request.path in settings.PUBLIC_API_PATHS:
            return self.get_response(request)
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return error_response(request, 401, "AUTH_INVALID")
        token = header.removeprefix("Bearer ").strip()
        try:
            claims = decode_access_token(token)
            request.principal = _principal(request.db, claims)
        except jwt.PyJWTError:
            return error_response(request, 401, "AUTH_INVALID")
        except Exception:
            logger.exception("request_id=%s", request.request_id)
            return error_response(request, 401, "AUTH_INVALID")
        if request.principal is None:
            return error_response(request, 401, "AUTH_INVALID")
        return self.get_response(request)


def _principal(session, claims):
    from modules.persistence.tables import Assignment, User

    try:
        user_id = uuid.UUID(claims["sub"])
        tenant_id = uuid.UUID(claims["tenant_id"])
    except (KeyError, ValueError):
        return None
    user = session.get(User, user_id)
    if user is None or user.status != "active" or user.tenant_id != tenant_id:
        return None
    assignment = session.query(Assignment).filter(Assignment.user_id == user.id).one_or_none()
    support = list(assignment.support_functions or []) if assignment else []
    return Principal(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        shelter_id=assignment.shelter_id if assignment else None,
        block_id=assignment.block_id if assignment else None,
        permissions=permissions_for(user.role, support, list(user.grants or [])),
        support_functions=support,
        status=user.status,
    )
