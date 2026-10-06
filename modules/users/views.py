from common.api.base import BaseAPIView
from common.api.http import respond
from modules.schemas.bodies import UserCreate, UserListQuery, UserUpdate
from modules.services import reads, records


class UserListView(BaseAPIView):
    def get(self, request):
        self.ensure("user.read")
        self.query_schema = UserListQuery
        data, meta = reads.list_users(request.db, request.principal, self.parse_query())
        return respond(request, data, extra_meta=meta)

    def post(self, request):
        self.ensure("user.manage")
        self.request_schema = UserCreate
        data = records.create_user(request.db, request.principal, self.parse_body(), request.request_id)
        return respond(request, data, status=201)


class UserDetailView(BaseAPIView):
    required_permission = "user.manage"

    def patch(self, request, user_id):
        self.request_schema = UserUpdate
        data = records.update_user(request.db, request.principal, user_id, self.parse_body(), request.request_id)
        return respond(request, data)
