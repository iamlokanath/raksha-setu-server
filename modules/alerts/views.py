from common.api.base import BaseAPIView
from common.api.http import respond
from modules.schemas.bodies import AlertListQuery, AlertTransition
from modules.services import reads, records

PERMISSIONS = {
    "acknowledge": "alert.acknowledge",
    "plan": "alert.plan",
    "start": "alert.progress",
    "resolve": "alert.resolve",
    "close": "alert.close",
}


class AlertListView(BaseAPIView):
    required_permission = "alert.read"
    query_schema = AlertListQuery

    def get(self, request):
        data, meta = reads.list_alerts(request.db, request.principal, self.parse_query())
        return respond(request, data, extra_meta=meta)


class AlertDetailView(BaseAPIView):
    required_permission = "alert.read"

    def get(self, request, alert_id):
        return respond(request, reads.get_alert(request.db, request.principal, alert_id))


class _Transition(BaseAPIView):
    request_schema = AlertTransition
    action_name = ""

    def post(self, request, alert_id):
        self.ensure(PERMISSIONS[self.action_name])
        body = self.parse_body()
        data = records.transition_alert(request.db, request.principal, alert_id, self.action_name, body.note, request.request_id)
        return respond(request, data)


class AlertAcknowledgeView(_Transition):
    action_name = "acknowledge"


class AlertPlanView(_Transition):
    action_name = "plan"


class AlertStartView(_Transition):
    action_name = "start"


class AlertResolveView(_Transition):
    action_name = "resolve"


class AlertCloseView(_Transition):
    action_name = "close"
