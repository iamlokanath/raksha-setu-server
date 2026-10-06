from common.api.base import BaseAPIView
from common.api.http import respond
from modules.schemas.bodies import ResourceListQuery
from modules.services import reads


class ShelterResourceView(BaseAPIView):
    required_permission = "resource.read"

    def get(self, request, shelter_id):
        return respond(request, reads.shelter_resources(request.db, request.principal, shelter_id))


class ResourceListView(BaseAPIView):
    required_permission = "resource.read"
    query_schema = ResourceListQuery

    def get(self, request):
        data, meta = reads.list_resources(request.db, request.principal, self.parse_query())
        return respond(request, data, extra_meta=meta)
