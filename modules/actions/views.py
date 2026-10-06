from common.api.base import BaseAPIView
from common.api.http import respond
from modules.schemas.bodies import ActionDecision, ActionListQuery, ActionModify, ReceiptBody
from modules.services import reads, records


class ActionListView(BaseAPIView):
    required_permission = "action.read"
    query_schema = ActionListQuery

    def get(self, request):
        data, meta = reads.list_actions(request.db, request.principal, self.parse_query())
        return respond(request, data, extra_meta=meta)


class ActionDetailView(BaseAPIView):
    required_permission = "action.read"

    def get(self, request, action_id):
        return respond(request, reads.get_action(request.db, request.principal, action_id))


class ActionApproveView(BaseAPIView):
    required_permission = "action.approve"
    request_schema = ActionDecision

    def post(self, request, action_id):
        body = self.parse_body()
        data = records.decide_action(request.db, request.principal, action_id, "approved", body.note, None, request.request_id)
        return respond(request, data)


class ActionModifyView(BaseAPIView):
    required_permission = "action.approve"
    request_schema = ActionModify

    def post(self, request, action_id):
        body = self.parse_body()
        data = records.decide_action(request.db, request.principal, action_id, "modified", body.note, body.quantity, request.request_id)
        return respond(request, data)


class ActionRejectView(BaseAPIView):
    required_permission = "action.approve"
    request_schema = ActionDecision

    def post(self, request, action_id):
        body = self.parse_body()
        data = records.decide_action(request.db, request.principal, action_id, "rejected", body.note, None, request.request_id)
        return respond(request, data)


class ActionConfirmReceiptView(BaseAPIView):
    required_permission = "action.confirm_receipt"
    request_schema = ReceiptBody

    def post(self, request, action_id):
        body = self.parse_body()
        data = records.confirm_receipt(request.db, request.principal, action_id, body.quantity, body.unit, request.request_id)
        return respond(request, data)
