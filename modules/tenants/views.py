from common.api.base import BaseAPIView
from common.api.http import respond
from modules.schemas.bodies import BlockCreate, ConfigurationBody, TenantCreate
from modules.services import reads, records
from modules.services.scope import parse_uuid


class TenantCreateView(BaseAPIView):
    required_permission = "tenant.manage"
    request_schema = TenantCreate

    def post(self, request):
        data = records.create_tenant(request.db, request.principal, self.parse_body(), request.request_id)
        return respond(request, data, status=201)


class TenantDetailView(BaseAPIView):
    def get(self, request, tenant_id):
        if request.principal is None:
            self.ensure("shelter.read")
        return respond(request, reads.get_tenant(request.db, request.principal, tenant_id))


class BlockCreateView(BaseAPIView):
    request_schema = BlockCreate

    def post(self, request, tenant_id):
        if not (request.principal.allows("tenant.manage") or request.principal.allows("user.manage")):
            self.ensure("tenant.manage")
        data = records.create_block(request.db, request.principal, tenant_id, self.parse_body(), request.request_id)
        return respond(request, data, status=201)


class TenantConfigurationView(BaseAPIView):
    def get(self, request, tenant_id):
        if not (request.principal.allows("tenant.manage") or request.principal.allows("user.manage")):
            self.ensure("tenant.manage")
        return respond(request, reads.get_configuration(request.db, request.principal, tenant_id))

    def put(self, request, tenant_id):
        if not (request.principal.allows("tenant.manage") or request.principal.allows("user.manage")):
            self.ensure("tenant.manage")
        self.request_schema = ConfigurationBody
        data = records.save_configuration(request.db, request.principal, tenant_id, self.parse_body())
        return respond(request, data)
