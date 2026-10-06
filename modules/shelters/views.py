from common.api.base import BaseAPIView
from common.api.http import respond
from modules.presenters import shelter_out
from modules.schemas.bodies import ShelterCreate, ShelterListQuery, ShelterUpdate
from modules.services import reads, records
from modules.services.scope import shelter_or_404


class ShelterListView(BaseAPIView):
    def get(self, request):
        self.ensure("shelter.read")
        self.query_schema = ShelterListQuery
        data, meta = reads.list_shelters(request.db, request.principal, self.parse_query())
        return respond(request, data, extra_meta=meta)

    def post(self, request):
        self.ensure("shelter.register")
        self.request_schema = ShelterCreate
        data = records.create_shelter(request.db, request.principal, self.parse_body(), request.request_id)
        return respond(request, data, status=201)


class ShelterDetailView(BaseAPIView):
    def get(self, request, shelter_id):
        self.ensure("shelter.read")
        return respond(request, shelter_out(shelter_or_404(request.db, request.principal, shelter_id)))

    def patch(self, request, shelter_id):
        self.ensure("shelter.update")
        self.request_schema = ShelterUpdate
        data = records.update_shelter(request.db, request.principal, shelter_id, self.parse_body(), request.request_id)
        return respond(request, data)
