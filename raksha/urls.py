from django.urls import path

from modules.actions.views import (
    ActionApproveView,
    ActionConfirmReceiptView,
    ActionDetailView,
    ActionListView,
    ActionModifyView,
    ActionRejectView,
)
from modules.alerts.views import (
    AlertAcknowledgeView,
    AlertCloseView,
    AlertDetailView,
    AlertListView,
    AlertPlanView,
    AlertResolveView,
    AlertStartView,
)
from modules.audit.views import AuditListView
from modules.auth.views import LoginView, LogoutView, MeView, RefreshView
from modules.dashboard.views import DashboardSheltersView, DashboardSummaryView
from modules.openapi.views import DocsView, SchemaView
from modules.reports.views import ReportDetailView, ReportListView, ShelterReportListView
from modules.resources.views import ResourceListView, ShelterResourceView
from modules.shelters.views import ShelterDetailView, ShelterListView
from modules.sync.views import SyncBatchDetailView, SyncBatchCreateView
from modules.tenants.views import BlockCreateView, TenantConfigurationView, TenantCreateView, TenantDetailView
from modules.users.views import UserDetailView, UserListView

urlpatterns = [
    path("api/v1/docs", DocsView.as_view()),
    path("api/v1/schema", SchemaView.as_view()),
    path("api/v1/auth/login", LoginView.as_view()),
    path("api/v1/auth/refresh", RefreshView.as_view()),
    path("api/v1/auth/logout", LogoutView.as_view()),
    path("api/v1/auth/me", MeView.as_view()),
    path("api/v1/tenants/", TenantCreateView.as_view()),
    path("api/v1/tenants/<uuid:tenant_id>", TenantDetailView.as_view()),
    path("api/v1/tenants/<uuid:tenant_id>/blocks", BlockCreateView.as_view()),
    path("api/v1/tenants/<uuid:tenant_id>/configuration", TenantConfigurationView.as_view()),
    path("api/v1/users/", UserListView.as_view()),
    path("api/v1/users/<uuid:user_id>", UserDetailView.as_view()),
    path("api/v1/shelters/", ShelterListView.as_view()),
    path("api/v1/shelters/<uuid:shelter_id>", ShelterDetailView.as_view()),
    path("api/v1/shelters/<uuid:shelter_id>/reports", ShelterReportListView.as_view()),
    path("api/v1/shelters/<uuid:shelter_id>/resources", ShelterResourceView.as_view()),
    path("api/v1/reports/", ReportListView.as_view()),
    path("api/v1/reports/<uuid:report_id>", ReportDetailView.as_view()),
    path("api/v1/resources/", ResourceListView.as_view()),
    path("api/v1/alerts/", AlertListView.as_view()),
    path("api/v1/alerts/<uuid:alert_id>", AlertDetailView.as_view()),
    path("api/v1/alerts/<uuid:alert_id>/acknowledge", AlertAcknowledgeView.as_view()),
    path("api/v1/alerts/<uuid:alert_id>/plan", AlertPlanView.as_view()),
    path("api/v1/alerts/<uuid:alert_id>/start", AlertStartView.as_view()),
    path("api/v1/alerts/<uuid:alert_id>/resolve", AlertResolveView.as_view()),
    path("api/v1/alerts/<uuid:alert_id>/close", AlertCloseView.as_view()),
    path("api/v1/actions/", ActionListView.as_view()),
    path("api/v1/actions/<uuid:action_id>", ActionDetailView.as_view()),
    path("api/v1/actions/<uuid:action_id>/approve", ActionApproveView.as_view()),
    path("api/v1/actions/<uuid:action_id>/modify", ActionModifyView.as_view()),
    path("api/v1/actions/<uuid:action_id>/reject", ActionRejectView.as_view()),
    path("api/v1/actions/<uuid:action_id>/confirm-receipt", ActionConfirmReceiptView.as_view()),
    path("api/v1/dashboard/summary", DashboardSummaryView.as_view()),
    path("api/v1/dashboard/shelters", DashboardSheltersView.as_view()),
    path("api/v1/sync/reports", SyncBatchCreateView.as_view()),
    path("api/v1/sync/batches/<uuid:batch_id>", SyncBatchDetailView.as_view()),
    path("api/v1/audit/", AuditListView.as_view()),
]
