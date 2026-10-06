from common.api.base import BaseAPIView
from common.api.errors import ApiError
from common.api.http import empty, respond
from modules.schemas.bodies import LoginRequest, LogoutRequest, RefreshRequest
from modules.services import auth_service


class LoginView(BaseAPIView):
    request_schema = LoginRequest

    def post(self, request):
        body = self.parse_body()
        try:
            data = auth_service.login(request.db, body.username, body.password, request.request_id)
        except ApiError:
            request.persist_side_effects = True
            raise
        return respond(request, data)


class RefreshView(BaseAPIView):
    request_schema = RefreshRequest

    def post(self, request):
        body = self.parse_body()
        try:
            data = auth_service.refresh(request.db, body.refresh_token, request.request_id)
        except ApiError:
            request.persist_side_effects = True
            raise
        return respond(request, data)


class LogoutView(BaseAPIView):
    request_schema = LogoutRequest

    def post(self, request):
        body = self.parse_body()
        auth_service.logout(request.db, request.principal, body.refresh_token, request.request_id)
        return empty()


class MeView(BaseAPIView):
    def get(self, request):
        return respond(request, auth_service.me(request.db, request.principal))
