from common.api.base import BaseAPIView
from common.api.http import respond
from modules.presenters import report_out
from modules.schemas.bodies import ReportCreate, ReportListQuery
from modules.services import reads
from modules.services.report_service import submit
from modules.services.scope import parse_uuid, shelter_or_404


class ReportListView(BaseAPIView):
    def get(self, request):
        self.ensure("report.read")
        self.query_schema = ReportListQuery
        data, meta = reads.list_reports(request.db, request.principal, self.parse_query())
        return respond(request, data, extra_meta=meta)

    def post(self, request):
        self.ensure("report.submit")
        self.request_schema = ReportCreate
        result = submit(request.db, request.principal, self.parse_body(), request.request_id)
        return respond(request, result["data"], status=result["status"], extra_meta=result["meta"])


class ReportDetailView(BaseAPIView):
    required_permission = "report.read"

    def get(self, request, report_id):
        from modules.persistence.tables import ShelterReport

        report = request.db.get(ShelterReport, report_id)
        if report is None:
            from common.api.errors import ApiError

            raise ApiError(404, "NOT_FOUND")
        shelter_or_404(request.db, request.principal, report.shelter_id)
        return respond(request, report_out(report))


class ShelterReportListView(BaseAPIView):
    required_permission = "report.read"

    def get(self, request, shelter_id):
        self.query_schema = ReportListQuery
        data, meta = reads.list_reports(request.db, request.principal, self.parse_query(), shelter_id=shelter_id)
        return respond(request, data, extra_meta=meta)
