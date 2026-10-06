import json
import logging
from datetime import datetime

from django.http import HttpResponse, JsonResponse

from common.timeutil import utcnow

logger = logging.getLogger("raksha")


class Encoder(json.JSONEncoder):
    def default(self, value):
        if isinstance(value, datetime):
            return value.isoformat()
        return super().default(value)


def meta(request, extra: dict | None = None) -> dict:
    payload = {"request_id": request.request_id, "timestamp": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
    if extra:
        payload.update(extra)
    return payload


def respond(request, data, status=200, extra_meta=None):
    body = {"data": data, "meta": meta(request, extra_meta)}
    return JsonResponse(body, status=status, encoder=Encoder)


def empty(status=204):
    return HttpResponse(status=status)


def error_response(request, status: int, code: str, details: list | None = None):
    request_id = getattr(request, "request_id", None)
    body = {"error": {"code": code, "details": details or [], "request_id": request_id}}
    if status >= 500:
        logger.error("request_id=%s code=%s", request_id, code)
    return JsonResponse(body, status=status)
