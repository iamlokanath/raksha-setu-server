from common.api.base import BaseAPIView
from common.api.http import respond
from modules.schemas.bodies import AuditListQuery
from modules.services import reads


class AuditListView(BaseAPIView):
    required_permission = "audit.read"
    query_schema = AuditListQuery

    def get(self, request):
        data, meta = reads.list_audit(request.db, request.principal, self.parse_query())
        return respond(request, data, extra_meta=meta)
