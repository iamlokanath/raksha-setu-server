from common.api.base import BaseAPIView
from common.api.http import respond
from modules.schemas.bodies import SyncBatchCreate
from modules.services import reads, records


class SyncBatchCreateView(BaseAPIView):
    required_permission = "report.submit"
    request_schema = SyncBatchCreate

    def post(self, request):
        data = records.create_sync_batch(request.db, request.principal, self.parse_body(), request.request_id)
        return respond(request, data, status=202)


class SyncBatchDetailView(BaseAPIView):
    def get(self, request, batch_id):
        if not (request.principal.allows("report.submit") or request.principal.allows("report.read")):
            self.ensure("report.read")
        return respond(request, reads.sync_batch(request.db, request.principal, batch_id))
