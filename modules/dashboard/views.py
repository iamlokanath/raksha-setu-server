from common.api.base import BaseAPIView
from common.api.http import respond
from modules.schemas.bodies import DashboardShelterQuery
from modules.services import reads


class DashboardSummaryView(BaseAPIView):
    required_permission = "dashboard.read"

    def get(self, request):
        block_id = None
        if request.principal.role == "block_officer":
            block_id = request.principal.block_id
        return respond(request, reads.dashboard_summary(request.db, request.principal, block_id))


class DashboardSheltersView(BaseAPIView):
    required_permission = "dashboard.read"
    query_schema = DashboardShelterQuery

    def get(self, request):
        data, meta = reads.dashboard_shelters(request.db, request.principal, self.parse_query())
        return respond(request, data, extra_meta=meta)
