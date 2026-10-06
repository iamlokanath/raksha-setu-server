import json
import logging

from django.views import View
from pydantic import ValidationError

from common.api.errors import ApiError
from common.api.http import error_response

logger = logging.getLogger("raksha")

PYDANTIC_CODES = {
    "missing": "REQUIRED",
    "greater_than_equal": "MIN_VALUE",
    "less_than_equal": "MAX_VALUE",
    "string_too_short": "REQUIRED",
    "string_too_long": "MAX_LENGTH",
    "extra_forbidden": "UNKNOWN_FIELD",
    "literal_error": "INVALID_CHOICE",
    "enum": "INVALID_CHOICE",
    "int_parsing": "INVALID",
    "float_parsing": "INVALID",
    "uuid_parsing": "INVALID",
    "datetime_parsing": "INVALID",
    "list_type": "INVALID",
    "dict_type": "INVALID",
    "too_short": "REQUIRED",
    "too_long": "MAX_LENGTH",
}


def _field_name(loc) -> str:
    parts: list[str] = []
    for part in loc:
        if isinstance(part, int) and parts:
            parts[-1] = f"{parts[-1]}[{part}]"
        else:
            parts.append(str(part))
    return ".".join(parts)


def pydantic_details(exc: ValidationError) -> list[dict]:
    details = []
    for err in exc.errors():
        field = _field_name(err.get("loc", []))
        if err.get("type") == "value_error":
            message = err.get("msg", "INVALID")
            code = message.split("Value error, ")[-1]
        else:
            code = PYDANTIC_CODES.get(err.get("type"), "INVALID")
        details.append({"field": field, "code": code})
    return details


class BaseAPIView(View):
    request_schema = None
    query_schema = None
    required_permission = None

    def ensure(self, permission: str) -> None:
        principal = getattr(self.request, "principal", None)
        if principal is None:
            raise ApiError(401, "AUTH_INVALID")
        if not principal.allows(permission):
            raise ApiError(403, "PERMISSION_DENIED")

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        try:
            if self.required_permission:
                self.ensure(self.required_permission)
            return super().dispatch(request, *args, **kwargs)
        except ApiError as exc:
            return error_response(request, exc.status, exc.code, exc.details)
        except Exception:
            logger.exception("request_id=%s", getattr(request, "request_id", None))
            return error_response(request, 500, "INTERNAL_ERROR")

    def parse_body(self):
        raw = self.request.body
        if not raw:
            data = {}
        else:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                raise ApiError(400, "VALIDATION_ERROR")
        if not isinstance(data, dict):
            raise ApiError(400, "VALIDATION_ERROR")
        try:
            return self.request_schema.model_validate(data)
        except ValidationError as exc:
            raise ApiError(400, "VALIDATION_ERROR", details=pydantic_details(exc))

    def parse_query(self):
        data = {key: self.request.GET.get(key) for key in self.request.GET.keys()}
        if self.query_schema is None:
            if data:
                raise ApiError(400, "VALIDATION_ERROR", details=[{"field": key, "code": "UNKNOWN_FIELD"} for key in data])
            return None
        try:
            return self.query_schema.model_validate(data)
        except ValidationError as exc:
            raise ApiError(400, "VALIDATION_ERROR", details=pydantic_details(exc))
