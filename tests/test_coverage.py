import json
import uuid
from datetime import datetime, timedelta, timezone
from io import StringIO
from types import SimpleNamespace

import jwt
import pytest
from django.conf import settings
from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory

from common.api.base import BaseAPIView
from common.api.errors import ApiError
from common.api.http import Encoder, empty, error_response
from common.authz.passwords import hash_password, verify_password
from common.authz.principal import Principal, permissions_for
from common.authz.tokens import encode_access_token
from common.db.base import new_id
from common.db.session import get_engine, get_session, reset_engine
from common.events.bus import drain, publish, subscribe
from common.timeutil import as_utc, isoformat, utcnow
from integrations.inbound import ingest
from integrations.sso.port import SsoAuthenticationProvider
from modules.persistence.tables import (
    Alert,
    Assignment,
    Outbox,
    RefreshToken,
    ResourceSnapshot,
    Shelter,
    TenantConfiguration,
    User,
)
from modules.pipeline.evaluate import capacity_severity, occupancy_band, priority_band, priority_score, shortage_severity
from modules.pipeline.handlers import on_capacity, on_shortage, on_sync_batch
from modules.schemas.bodies import (
    ConfigurationBody,
    LoginRequest,
    PriorityConfig,
    ReportCreate,
    ResourceRule,
    ShelterCreate,
    UserCreate,
)
from modules.services.reads import list_reports
from modules.services.report_service import _reported_at, _resource, submit
from modules.services.scope import block_in_tenant, in_scope, parse_uuid, require, scoped_shelters, user_in_tenant
from tests.conftest import api, approve_config, login, make_world, report_body


def _minutes(offset: int):
    return utcnow() - timedelta(hours=6) + timedelta(minutes=offset)


def _users(client, token):
    status, body = api(client, "get", "/api/v1/users/?page_size=100", token)
    assert status == 200, body
    return {row["username"]: row for row in body["data"]}


def test_passwords_tokens_time_and_schema_edges():
    assert new_id()
    assert verify_password("secret", None) is False
    assert verify_password("secret", "") is False
    assert verify_password("secret", "not-a-hash") is False
    assert verify_password("secret", "md5$1$salt$digest") is False
    stored = hash_password("secret")
    assert verify_password("secret", stored) is True
    assert verify_password("other", stored) is False
    assert isoformat(None) is None
    naive = datetime(2020, 1, 1, 0, 0, 0)
    assert as_utc(naive).tzinfo == timezone.utc
    assert as_utc(datetime(2020, 1, 1, tzinfo=timezone.utc)).tzinfo == timezone.utc
    encoder = Encoder()
    assert encoder.default(datetime(2020, 1, 1, tzinfo=timezone.utc)).startswith("2020-01-01")
    with pytest.raises(TypeError):
        encoder.default(1)
    assert empty().status_code == 204
    response = error_response(SimpleNamespace(request_id="req-1"), 500, "INTERNAL_ERROR")
    assert response.status_code == 500
    rule = {"urgent_below": 5, "attention_below": 15}
    assert shortage_severity(10, rule) == "attention"
    assert shortage_severity(20, rule) is None
    assert capacity_severity(1, 0, {"urgent_at_ratio": 1, "attention_at_ratio": 0.8}) is None
    assert occupancy_band(None, 10, {"urgent_at_ratio": 1, "attention_at_ratio": 0.8}) == "unknown"
    assert occupancy_band(1, 10, None) == "unknown"
    config = {
        "severity_scores": {"none": 0, "attention": 0.5, "urgent": 1},
        "weights": {"shortage_urgency": 0.4, "vulnerable_population": 0.2, "occupancy_pressure": 0.2, "issue_age": 0.2},
        "vulnerable_cap": 50,
        "age_cap_hours": 48,
        "bands": {"high": 0.6, "medium": 0.3},
    }
    factors = {"shortage_urgency": "urgent", "vulnerable_population": 50, "occupancy_pressure": 1, "issue_age_seconds": 48 * 3600}
    high = priority_score(factors, config)
    assert priority_band(high, config) == "high"
    assert priority_band(0.4, config) == "medium"
    assert priority_band(0.1, config) == "low"
    assert priority_band(None, config) == "unscored"
    assert priority_band(1, None) == "unscored"
    assert priority_score(factors, None) is None
    assert "report.submit" not in permissions_for("volunteer", ["training"], [])
    assert "report.submit" in permissions_for("volunteer", ["reporting_support"], None)
    assert "tenant.manage" in permissions_for("district_officer", [], ["tenant.manage", "not-a-grant"])
    with pytest.raises(ValueError):
        ResourceRule(attention_below=1, urgent_below=2, surplus_above=3, unit="kg")
    with pytest.raises(ValueError):
        PriorityConfig(
            weights={"shortage_urgency": -1, "vulnerable_population": 0, "occupancy_pressure": 0, "issue_age": 0},
            vulnerable_cap=1,
            age_cap_hours=1,
            severity_scores={"none": 0, "attention": 1, "urgent": 2},
            bands={"high": 0.6, "medium": 0.3},
        )
    with pytest.raises(ValueError):
        PriorityConfig(
            weights={"shortage_urgency": 1, "vulnerable_population": 0, "occupancy_pressure": 0, "issue_age": 0},
            vulnerable_cap=1,
            age_cap_hours=1,
            severity_scores={"none": 0, "attention": 1},
            bands={"high": 0.6, "medium": 0.3},
        )
    with pytest.raises(ValueError):
        PriorityConfig(
            weights={"shortage_urgency": 1, "vulnerable_population": 0, "occupancy_pressure": 0, "issue_age": 0},
            vulnerable_cap=1,
            age_cap_hours=1,
            severity_scores={"none": 0, "attention": 1, "urgent": 2},
            bands={"high": 0.2, "medium": 0.3},
        )


def test_scope_and_report_helpers():
    session = get_session()
    principal = Principal(uuid.uuid4(), uuid.uuid4(), "volunteer", None, None, set(), [])
    with pytest.raises(ApiError) as denied:
        require(None, "shelter.read")
    assert denied.value.status == 401
    with pytest.raises(ApiError) as forbidden:
        require(principal, "shelter.read")
    assert forbidden.value.status == 403
    with pytest.raises(ApiError):
        parse_uuid("not-a-uuid", "shelter_id")
    with pytest.raises(ApiError):
        parse_uuid(None, "shelter_id")
    shelter = Shelter(
        tenant_id=principal.tenant_id,
        block_id=uuid.uuid4(),
        name="Orphan",
        location_label="None",
        capacity=10,
        warden_user_id=uuid.uuid4(),
        reporting_contact="000",
        operational_status="active",
        current_status="unknown",
    )
    assert in_scope(principal, shelter) is False
    other = Principal(uuid.uuid4(), uuid.uuid4(), "district_officer", None, None, set(), [])
    assert in_scope(other, shelter) is False
    block_principal = Principal(uuid.uuid4(), principal.tenant_id, "block_officer", None, uuid.uuid4(), set(), [])
    assert in_scope(block_principal, shelter) is False
    volunteer = Principal(uuid.uuid4(), principal.tenant_id, "volunteer", None, shelter.block_id, set(), [])
    assert in_scope(volunteer, shelter) is True
    assert scoped_shelters(session, principal).count() == 0
    with pytest.raises(ApiError):
        block_in_tenant(session, principal, uuid.uuid4())
    with pytest.raises(ApiError):
        user_in_tenant(session, principal, uuid.uuid4())
    with pytest.raises(ApiError):
        _reported_at("2020-01-01T00:00:00")
    with pytest.raises(ApiError):
        _resource(SimpleNamespace(resources=[]), "food")
    data = ReportCreate.model_validate(report_body(str(uuid.uuid4())))
    warden = Principal(uuid.uuid4(), principal.tenant_id, "warden", uuid.uuid4(), None, {"report.submit"}, [])
    session.add(TenantConfiguration(tenant_id=principal.tenant_id))
    session.add(shelter)
    session.commit()
    warden.tenant_id = shelter.tenant_id
    with pytest.raises(ApiError) as missing_shelter:
        submit(session, warden, data, "req")
    assert missing_shelter.value.status == 404
    volunteer_principal = Principal(uuid.uuid4(), shelter.tenant_id, "volunteer", shelter.id, None, {"report.submit"}, [])
    copied = report_body(str(shelter.id))
    with pytest.raises(ApiError) as volunteer_denied:
        submit(session, volunteer_principal, ReportCreate.model_validate(copied), "req")
    assert volunteer_denied.value.status == 403
    rows, _meta = list_reports(session, principal, SimpleNamespace(shelter_id=None, channel=None, from_time=None, to_time=None, page=1, page_size=20))
    assert rows == []
    session.close()


def test_settings_seed_wsgi_and_protocol(tmp_path, monkeypatch):
    from raksha import settings as raksha_settings

    monkeypatch.setattr(raksha_settings, "BASE_DIR", tmp_path)
    raksha_settings.load_env_file()
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nNOEQUALS\nCOVERAGE_ENV_PROBE=from-file\n", encoding="utf-8")
    monkeypatch.delenv("COVERAGE_ENV_PROBE", raising=False)
    raksha_settings.load_env_file()
    assert raksha_settings.os.environ["COVERAGE_ENV_PROBE"] == "from-file"
    assert raksha_settings.database_url("postgresql://db/raksha").startswith("postgresql+psycopg://")
    assert raksha_settings.database_url("postgres://db/raksha").startswith("postgresql+psycopg://")
    assert raksha_settings.database_url("sqlite://") == "sqlite://"

    err = StringIO()
    monkeypatch.setenv("SEED_PASSWORD", "short")
    call_command("seed", stderr=err)
    assert "at least 8" in err.getvalue()
    monkeypatch.setenv("SEED_PASSWORD", "pilot-pass-1")
    out = StringIO()
    call_command("seed", stdout=out)
    assert "ready" in out.getvalue()
    again = StringIO()
    call_command("seed", stdout=again)
    assert "already exists" in again.getvalue()

    import raksha.wsgi as wsgi

    assert wsgi.application is not None

    class Provider:
        def authenticate(self, credentials: dict) -> dict:
            return {"user_id": "local"}

    assert Provider().authenticate({})["user_id"] == "local"
    assert SsoAuthenticationProvider.authenticate(Provider(), {}) is None


def test_http_edges_auth_and_openapi(client):
    world = make_world()
    status, body = api(client, "post", "/api/v1/auth/login", body={"username": "missing", "password": "password-1"})
    assert status == 401
    status, body = api(client, "post", "/api/v1/auth/login", body={"username": "district", "password": "wrong-password"})
    assert status == 401
    status, login_body = api(client, "post", "/api/v1/auth/login", body={"username": "district", "password": "password-1"})
    assert status == 200
    access = login_body["data"]["access_token"]
    refresh = login_body["data"]["refresh_token"]
    status, me = api(client, "get", "/api/v1/auth/me", access)
    assert status == 200
    assert me["data"]["tenant_name"] == "District A"
    status, refreshed = api(client, "post", "/api/v1/auth/refresh", body={"refresh_token": refresh})
    assert status == 200
    status, reused = api(client, "post", "/api/v1/auth/refresh", body={"refresh_token": refresh})
    assert status == 401
    status, missing = api(client, "post", "/api/v1/auth/refresh", body={"refresh_token": "not-a-real-token"})
    assert status == 401
    new_refresh = refreshed["data"]["refresh_token"]
    status, _logout = api(client, "post", "/api/v1/auth/logout", access, {"refresh_token": "someone-elses-token"})
    assert status == 401
    status, logged_out = api(client, "post", "/api/v1/auth/logout", access, {"refresh_token": new_refresh})
    assert status == 204 and logged_out is None

    raw = client.post("/api/v1/auth/login", data="", content_type="application/json")
    assert raw.status_code == 400
    raw = client.post("/api/v1/auth/login", data="{not-json", content_type="application/json")
    assert raw.status_code == 400
    raw = client.post("/api/v1/auth/login", data="[]", content_type="application/json")
    assert raw.status_code == 400
    raw = client.get("/api/v1/shelters/?page=0", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert raw.status_code == 400
    options = client.options("/api/v1/shelters/", HTTP_ORIGIN="http://localhost:3000")
    assert options.status_code == 204
    assert options["Access-Control-Allow-Origin"] == "http://localhost:3000"
    import common.middleware as middleware

    health = RequestFactory().get("/health")
    health.db = get_session()
    assert middleware.AuthMiddleware(lambda _request: HttpResponse("ok"))(health).status_code == 200
    health.db.close()
    assert client.get("/api/v1/auth/me", HTTP_AUTHORIZATION="Bearer not-a-jwt").status_code == 401
    bad_claims = jwt.encode({"role": "warden"}, settings.SECRET_KEY, algorithm="HS256")
    assert client.get("/api/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {bad_claims}").status_code == 401

    session = get_session()
    user = session.query(User).filter(User.username == "warden_a").one()
    user.status = "inactive"
    session.commit()
    inactive_token = encode_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
    session.close()
    assert client.get("/api/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {inactive_token}").status_code == 401

    session = get_session()
    district = session.query(User).filter(User.username == "district").one()
    session.add(
        RefreshToken(
            tenant_id=district.tenant_id,
            user_id=district.id,
            family_id=uuid.uuid4(),
            token_hash=__import__("common.authz.passwords", fromlist=["hash_token"]).hash_token("expired-refresh-token"),
            revoked=False,
            expires_at=utcnow() - timedelta(days=1),
            created_at=utcnow() - timedelta(days=2),
        )
    )
    orphan = User(
        tenant_id=district.tenant_id,
        name="No Assignment",
        username="orphan",
        role="district_officer",
        organization="District A",
        password_hash=hash_password("password-1"),
        grants=[],
        status="active",
    )
    session.add(orphan)
    session.commit()
    orphan_id = orphan.id
    session.close()
    status, expired = api(client, "post", "/api/v1/auth/refresh", body={"refresh_token": "expired-refresh-token"})
    assert status == 401
    admin = login(client, "admin")
    status, patched = api(client, "patch", f"/api/v1/users/{orphan_id}", admin, {"name": "Named"})
    assert status == 200 and patched["data"]["name"] == "Named"

    status, schema = api(client, "get", "/api/v1/schema")
    assert status == 200 and "/api/v1/auth/login" in schema["paths"]
    docs = client.get("/api/v1/docs")
    assert docs.status_code == 200 and b"SwaggerUIBundle" in docs.content
    assert world["tenant"]


def test_auth_middleware_exceptions(client, monkeypatch):
    import common.middleware as middleware

    def explode(_token):
        raise RuntimeError("decode failed")

    monkeypatch.setattr(middleware, "decode_access_token", explode)
    status = client.get("/api/v1/auth/me", HTTP_AUTHORIZATION="Bearer anything").status_code
    assert status == 401

    def crash(_request):
        raise RuntimeError("view failed")

    request = RequestFactory().get("/api/v1/shelters/")
    request.request_id = "req-500"
    response = middleware.DatabaseMiddleware(crash)(request)
    assert response.status_code == 500


def test_view_dispatch_and_query_without_schema():
    class Boom(BaseAPIView):
        def get(self, request):
            raise RuntimeError("boom")

    request = RequestFactory().get("/api/v1/boom")
    request.request_id = "req"
    request.principal = Principal(uuid.uuid4(), uuid.uuid4(), "district_officer", None, None, {"shelter.read"}, [])
    assert Boom.as_view()(request).status_code == 500

    class Locked(BaseAPIView):
        required_permission = "shelter.read"

        def get(self, request):
            return HttpResponse("ok")

    anonymous = RequestFactory().get("/api/v1/locked")
    anonymous.principal = None
    anonymous.request_id = "req"
    assert Locked.as_view()(anonymous).status_code == 401

    view = BaseAPIView()
    view.request_schema = LoginRequest
    view.query_schema = None
    empty_request = RequestFactory().post("/api/v1/auth/login", data=b"", content_type="application/json")
    view.request = empty_request
    with pytest.raises(ApiError):
        view.parse_body()
    view.request = RequestFactory().get("/api/v1/x?extra=1")
    with pytest.raises(ApiError) as unknown:
        view.parse_query()
    assert unknown.value.details[0]["code"] == "UNKNOWN_FIELD"
    view.request = RequestFactory().get("/api/v1/x")
    assert view.parse_query() is None


def test_directory_configuration_and_filters(client):
    world = make_world()
    admin = login(client, "admin")
    district = login(client, "district")
    block = login(client, "block")
    people = _users(client, admin)
    status, denied = api(client, "get", f"/api/v1/tenants/{world['tenant']}/configuration", district)
    assert status == 403
    status, empty_config = api(client, "get", f"/api/v1/tenants/{world['tenant']}/configuration", admin)
    assert status == 200 and empty_config["data"]["shortage"] is None
    status, surplus = api(client, "get", "/api/v1/resources/?surplus=true", district)
    assert status == 422 and surplus["error"]["code"] == "CONFIGURATION_REQUIRED"
    status, priority = api(client, "get", "/api/v1/dashboard/shelters?priority=high", district)
    assert status == 422
    status, occupancy = api(client, "get", "/api/v1/dashboard/shelters?occupancy=urgent", district)
    assert status == 422
    status, created = api(
        client,
        "post",
        "/api/v1/tenants/",
        admin,
        {"name": "District C", "code": "c"},
    )
    assert status == 201
    status, duplicate = api(client, "post", "/api/v1/tenants/", admin, {"name": "District C", "code": "c"})
    assert status == 409
    status, tenant = api(client, "get", f"/api/v1/tenants/{created['data']['id']}", admin)
    assert status == 200 and tenant["data"]["code"] == "c"
    status, hidden = api(client, "get", f"/api/v1/tenants/{world['other']}", district)
    assert status == 404
    status, missing_tenant = api(client, "get", f"/api/v1/tenants/{uuid.uuid4()}", admin)
    assert status == 404
    status, block_denied = api(client, "post", f"/api/v1/tenants/{world['tenant']}/blocks", district, {"name": "East", "code": "east"})
    assert status == 403
    status, other_block = api(client, "post", f"/api/v1/tenants/{world['other']}/blocks", district, {"name": "East", "code": "east"})
    assert status == 403
    status, new_block = api(client, "post", f"/api/v1/tenants/{world['tenant']}/blocks", admin, {"name": "East", "code": "east"})
    assert status == 201
    status, duplicate_block = api(client, "post", f"/api/v1/tenants/{world['tenant']}/blocks", admin, {"name": "East", "code": "east"})
    assert status == 409
    status, bad_rule = api(
        client,
        "put",
        f"/api/v1/tenants/{world['tenant']}/configuration",
        admin,
        {"capacity": {"attention_at_ratio": 1, "urgent_at_ratio": 0.5}},
    )
    assert status == 400
    approve_config(client, admin, world["tenant"])
    status, other_config = api(client, "put", f"/api/v1/tenants/{world['other']}/configuration", district, {"shortage": None, "capacity": None, "priority": None})
    assert status == 403 and other_config["error"]["code"] == "PERMISSION_DENIED"

    status, bad_user = api(
        client,
        "post",
        "/api/v1/users/",
        admin,
        {"name": "Bad", "username": "bad", "password": "password-1", "role": "warden", "organization": "District A", "grants": ["user.manage"]},
    )
    assert status == 400
    status, warden = api(
        client,
        "post",
        "/api/v1/users/",
        admin,
        {
            "name": "Warden C",
            "username": "warden_c",
            "password": "password-1",
            "role": "warden",
            "organization": "District A",
            "shelter_id": world["shelter_a"],
        },
    )
    assert status == 201
    status, duplicate_user = api(
        client,
        "post",
        "/api/v1/users/",
        admin,
        {
            "name": "Warden C",
            "username": "warden_c",
            "password": "password-1",
            "role": "warden",
            "organization": "District A",
            "shelter_id": world["shelter_a"],
        },
    )
    assert status == 409
    status, volunteer = api(
        client,
        "post",
        "/api/v1/users/",
        admin,
        {
            "name": "Reporter",
            "username": "reporter",
            "password": "password-1",
            "role": "volunteer",
            "organization": "District A",
            "shelter_id": world["shelter_a"],
            "support_functions": ["reporting_support"],
        },
    )
    assert status == 201
    status, trainer = api(
        client,
        "post",
        "/api/v1/users/",
        admin,
        {
            "name": "Trainer",
            "username": "trainer",
            "password": "password-1",
            "role": "volunteer",
            "organization": "District A",
            "block_id": world["block"],
            "support_functions": ["training"],
        },
    )
    assert status == 201
    status, officer = api(
        client,
        "post",
        "/api/v1/users/",
        admin,
        {
            "name": "East Officer",
            "username": "east",
            "password": "password-1",
            "role": "block_officer",
            "organization": "District A",
            "block_id": new_block["data"]["id"],
        },
    )
    assert status == 201
    status, listed = api(client, "get", f"/api/v1/users/?role=warden&shelter_id={world['shelter_a']}&page=1&page_size=1", admin)
    assert status == 200 and listed["meta"]["total"] >= 1
    status, by_block = api(client, "get", f"/api/v1/users/?block_id={world['block']}", admin)
    assert status == 200 and any(row["username"] == "trainer" for row in by_block["data"])
    status, renamed = api(client, "patch", f"/api/v1/users/{warden['data']['id']}", admin, {"organization": "Field"})
    assert status == 200
    status, moved = api(client, "patch", f"/api/v1/users/{trainer['data']['id']}", admin, {"shelter_id": world["shelter_b"], "block_id": None, "support_functions": ["training"]})
    assert status == 200 and moved["data"]["shelter_id"] == world["shelter_b"]
    reporter = login(client, "reporter")
    assert "report.submit" in api(client, "get", "/api/v1/auth/me", reporter)[1]["data"]["permissions"]
    status, trainer_report = api(client, "post", "/api/v1/reports/", login(client, "trainer"), report_body(world["shelter_b"]))
    assert status == 403
    status, inactive = api(client, "patch", f"/api/v1/users/{people['warden_b']['id']}", admin, {"status": "inactive"})
    assert status == 200 and inactive["data"]["status"] == "inactive"
    status, shelters = api(client, "get", f"/api/v1/shelters/?operational_status=active&block_id={world['block']}&sort=current_status&page=1&page_size=1", district)
    assert status == 200 and shelters["meta"]["total"] == 2
    status, wrong_block = api(client, "get", f"/api/v1/shelters/?block_id={new_block['data']['id']}", block)
    assert status == 403
    status, outside = api(client, "get", f"/api/v1/shelters/?block_id={uuid.uuid4()}", district)
    assert status == 404
    east = login(client, "east")
    status, east_list = api(client, "get", "/api/v1/shelters/", east)
    assert status == 200 and east_list["data"] == []
    status, bad_shelter = api(
        client,
        "post",
        "/api/v1/shelters/",
        admin,
        {
            "name": "Bad",
            "block_id": world["block"],
            "location_label": "East",
            "latitude": 20,
            "capacity": 10,
            "warden_user_id": people["warden_a"]["id"],
            "reporting_contact": "333",
        },
    )
    assert status == 400
    status, range_error = api(
        client,
        "post",
        "/api/v1/shelters/",
        admin,
        {
            "name": "Bad",
            "block_id": world["block"],
            "location_label": "East",
            "latitude": 120,
            "longitude": 200,
            "capacity": 10,
            "warden_user_id": people["warden_a"]["id"],
            "reporting_contact": "333",
        },
    )
    assert status == 400
    status, wrong_warden = api(
        client,
        "post",
        "/api/v1/shelters/",
        admin,
        {
            "name": "Bad",
            "block_id": world["block"],
            "location_label": "East",
            "capacity": 10,
            "warden_user_id": people["district"]["id"],
            "reporting_contact": "333",
        },
    )
    assert status == 404
    status, shelter = api(
        client,
        "post",
        "/api/v1/shelters/",
        admin,
        {
            "name": "Shelter C",
            "block_id": new_block["data"]["id"],
            "location_label": "East school",
            "latitude": 20.1,
            "longitude": 85.1,
            "capacity": 40,
            "warden_user_id": people["warden_a"]["id"],
            "reporting_contact": "333",
        },
    )
    assert status == 201
    status, updated = api(
        client,
        "patch",
        f"/api/v1/shelters/{shelter['data']['id']}",
        district,
        {"name": "Shelter C2", "capacity": 41, "operational_status": "inactive", "reporting_contact": "334", "warden_user_id": people["warden_a"]["id"], "block_id": world["block"]},
    )
    assert status == 200 and updated["data"]["name"] == "Shelter C2"
    status, empty_patch = api(client, "patch", f"/api/v1/shelters/{world['shelter_a']}", district, {})
    assert status == 400
    status, detail = api(client, "get", f"/api/v1/shelters/{world['shelter_a']}", district)
    assert status == 200
    assert volunteer["data"]["username"] == "reporter"
    assert officer["data"]["username"] == "east"


def test_reports_alerts_actions_dashboard_and_sync(client):
    world = make_world()
    admin = login(client, "admin")
    district = login(client, "district")
    block = login(client, "block")
    warden_a = login(client, "warden_a")
    warden_b = login(client, "warden_b")
    approve_config(client, admin, world["tenant"])
    people = _users(client, admin)
    status, east_block = api(client, "post", f"/api/v1/tenants/{world['tenant']}/blocks", admin, {"name": "East", "code": "east"})
    assert status == 201
    status, _east_user = api(
        client,
        "post",
        "/api/v1/users/",
        admin,
        {"name": "East Officer", "username": "east", "password": "password-1", "role": "block_officer", "organization": "District A", "block_id": east_block["data"]["id"]},
    )
    assert status == 201
    east = login(client, "east")

    def submit(token, shelter_id, **kwargs):
        body = report_body(shelter_id, when=_minutes(kwargs.pop("minute")), **kwargs)
        return api(client, "post", "/api/v1/reports/", token, body), body

    (status, first), first_body = submit(warden_a, world["shelter_a"], minute=1, population=90, food=40, water=40, medicine=40)
    assert status == 201
    (status, cleared), _ = submit(warden_a, world["shelter_a"], minute=2, population=10, food=40, water=40, medicine=40)
    assert status == 201
    (status, attention), _ = submit(warden_b, world["shelter_b"], minute=3, population=10, food=10, water=20, medicine=1)
    assert status == 201
    (status, upgraded), _ = submit(warden_b, world["shelter_b"], minute=4, population=10, food=1, water=20, medicine=1)
    assert status == 201
    (status, downgraded), _ = submit(warden_b, world["shelter_b"], minute=5, population=10, food=10, water=20, medicine=1)
    assert status == 201
    (status, resolved), _ = submit(warden_b, world["shelter_b"], minute=6, population=10, food=40, water=1, medicine=1)
    assert status == 201
    assert first["data"]["applied_to_current"] is True
    assert cleared and attention and upgraded and downgraded and resolved

    status, other_shelter = api(client, "post", "/api/v1/reports/", warden_a, report_body(world["shelter_b"], when=_minutes(7)))
    assert status == 404
    status, naive = api(client, "post", "/api/v1/reports/", warden_a, {**report_body(world["shelter_a"]), "reported_at": "2020-01-01T00:00:00"})
    assert status == 400
    future = (utcnow() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    status, future_body = api(client, "post", "/api/v1/reports/", warden_a, {**report_body(world["shelter_a"]), "reported_at": future})
    assert status == 400
    broken = report_body(world["shelter_a"])
    broken["resources"] = [{"resource_type": "food", "quantity": 1, "unit": "kg"}]
    status, resource_set = api(client, "post", "/api/v1/reports/", warden_a, broken)
    assert status == 400
    indexed = report_body(world["shelter_a"])
    del indexed["resources"][0]["unit"]
    status, indexed_error = api(client, "post", "/api/v1/reports/", warden_a, indexed)
    assert status == 400 and "resources[0]" in indexed_error["error"]["details"][0]["field"]
    overflow = report_body(world["shelter_a"], population=1)
    overflow["vulnerability"]["children"] = 5
    status, overflow_body = api(client, "post", "/api/v1/reports/", warden_a, overflow)
    assert status == 400
    replay = report_body(world["shelter_a"], when=_minutes(8))
    assert api(client, "post", "/api/v1/reports/", warden_a, replay)[0] == 201
    assert api(client, "post", "/api/v1/reports/", warden_a, replay)[0] == 200
    assert api(client, "post", "/api/v1/reports/", warden_a, replay)[0] == 200

    status, reports = api(
        client,
        "get",
        f"/api/v1/reports/?shelter_id={world['shelter_a']}&channel=web&from=2020-01-01T00:00:00Z&to=2099-01-01T00:00:00Z",
        district,
    )
    assert status == 200 and reports["meta"]["total"] >= 1
    status, bad_time = api(client, "get", "/api/v1/reports/?from=yesterday", district)
    assert status == 400
    report_id = first["data"]["id"]
    status, report = api(client, "get", f"/api/v1/reports/{report_id}", district)
    assert status == 200
    status, missing_report = api(client, "get", f"/api/v1/reports/{uuid.uuid4()}", district)
    assert status == 404
    status, shelter_reports = api(client, "get", f"/api/v1/shelters/{world['shelter_a']}/reports?channel=web", warden_a)
    assert status == 200 and shelter_reports["data"]
    status, hidden_reports = api(client, "get", f"/api/v1/shelters/{world['shelter_b']}/reports", warden_a)
    assert status == 404

    status, stock = api(client, "get", f"/api/v1/shelters/{world['shelter_a']}/resources", district)
    assert status == 200
    status, surplus = api(client, "get", f"/api/v1/resources/?surplus=true&resource_type=food&block_id={world['block']}", district)
    assert status == 200 and surplus["data"]
    status, not_surplus = api(client, "get", "/api/v1/resources/?surplus=false", district)
    assert status == 200
    status, bad_surplus = api(client, "get", "/api/v1/resources/?surplus=maybe", district)
    assert status == 400
    status, wrong_resource_block = api(client, "get", f"/api/v1/resources/?block_id={east_block['data']['id']}", block)
    assert status == 403

    status, alerts = api(client, "get", f"/api/v1/alerts/?status=detected&severity=urgent&type=shortage&shelter_id={world['shelter_b']}&block_id={world['block']}&sort=severity", district)
    assert status == 200 and alerts["data"]
    status, wrong_alert_block = api(client, "get", f"/api/v1/alerts/?block_id={east_block['data']['id']}", block)
    assert status == 403
    alert_id = alerts["data"][0]["id"]
    status, alert = api(client, "get", f"/api/v1/alerts/{alert_id}", district)
    assert status == 200
    status, missing_alert = api(client, "get", f"/api/v1/alerts/{uuid.uuid4()}", district)
    assert status == 404
    status, illegal = api(client, "post", f"/api/v1/alerts/{alert_id}/close", district, {})
    assert status == 422
    for action in ("acknowledge", "plan", "start", "resolve", "close"):
        status, moved = api(client, "post", f"/api/v1/alerts/{alert_id}/{action}", district, {"note": action})
        assert status == 200, moved
        assert moved["data"]["status"] != "detected" or action == "acknowledge"

    status, actions = api(client, "get", f"/api/v1/actions/?decision=proposed&shelter_id={world['shelter_b']}&block_id={world['block']}", district)
    assert status == 200 and len(actions["data"]) >= 2
    status, wrong_action_block = api(client, "get", f"/api/v1/actions/?block_id={east_block['data']['id']}", block)
    assert status == 403
    status, page = api(client, "get", "/api/v1/actions/?page=2&page_size=1", district)
    assert status == 200
    action_ids = [row["id"] for row in actions["data"]]
    status, action = api(client, "get", f"/api/v1/actions/{action_ids[0]}", district)
    assert status == 200
    status, missing_action = api(client, "get", f"/api/v1/actions/{uuid.uuid4()}", district)
    assert status == 404
    status, outsider = api(client, "get", f"/api/v1/actions/{action_ids[0]}", east)
    assert status == 404
    status, early = api(client, "post", f"/api/v1/actions/{action_ids[0]}/confirm-receipt", warden_b, {"quantity": 1, "unit": "kg"})
    assert status == 422
    status, blocked = api(client, "post", f"/api/v1/actions/{action_ids[0]}/approve", block, {})
    assert status == 403
    status, approved = api(client, "post", f"/api/v1/actions/{action_ids[0]}/approve", district, {"note": "send"})
    assert status == 200 and approved["data"]["decision"] == "approved"
    status, source_receipt = api(client, "post", f"/api/v1/actions/{action_ids[0]}/confirm-receipt", warden_a, {"quantity": 1, "unit": "kg"})
    assert status == 404
    status, receipt = api(client, "post", f"/api/v1/actions/{action_ids[0]}/confirm-receipt", warden_b, {"quantity": 1, "unit": "kg"})
    assert status == 200 and receipt["data"]["status"] == "receipt_confirmed"
    status, again = api(client, "post", f"/api/v1/actions/{action_ids[0]}/approve", district, {})
    assert status == 422
    if len(action_ids) > 1:
        status, modified = api(client, "post", f"/api/v1/actions/{action_ids[1]}/modify", district, {"quantity": 2, "note": "less"})
        assert status == 200 and modified["data"]["approved_quantity"] == 2
    if len(action_ids) > 2:
        status, rejected = api(client, "post", f"/api/v1/actions/{action_ids[2]}/reject", district, {"note": "no"})
        assert status == 200
        status, rejected_receipt = api(client, "post", f"/api/v1/actions/{action_ids[2]}/confirm-receipt", warden_b, {"quantity": 1, "unit": "kg"})
        assert status == 422

    status, summary = api(client, "get", "/api/v1/dashboard/summary", block)
    assert status == 200 and "urgent_shelter_count" in summary["data"]
    status, rows = api(
        client,
        "get",
        f"/api/v1/dashboard/shelters?block_id={world['block']}&status=red&shortage_type=medicine&occupancy=below_attention&priority=low&page_size=5",
        district,
    )
    assert status == 200
    status, unknown = api(client, "get", "/api/v1/dashboard/shelters?occupancy=unknown&priority=unscored&status=unknown", district)
    assert status == 200
    status, wrong_dash = api(client, "get", f"/api/v1/dashboard/shelters?block_id={east_block['data']['id']}", block)
    assert status == 403
    status, missing_dash_block = api(client, "get", f"/api/v1/dashboard/shelters?block_id={uuid.uuid4()}", district)
    assert status == 404
    assert page["meta"]["page"] == 2
    assert rows["meta"]["page_size"] == 5
    assert unknown["meta"]["total"] >= 0

    historical = report_body(world["shelter_a"], when=_minutes(0), population=10)
    queued = report_body(world["shelter_a"], when=_minutes(20))
    foreign = report_body(world["shelter_b"], when=_minutes(21))
    status, batch = api(client, "post", "/api/v1/sync/reports", warden_a, {"reports": [historical, queued, queued, foreign]})
    assert status == 202
    status, batch_body = api(client, "get", f"/api/v1/sync/batches/{batch['data']['batch_id']}", warden_a)
    assert status == 200
    states = {item["state"] for item in batch_body["data"]["items"]}
    assert "rejected" in states
    status, officer_batch = api(client, "get", f"/api/v1/sync/batches/{batch['data']['batch_id']}", district)
    assert status == 200
    status, hidden_batch = api(client, "get", f"/api/v1/sync/batches/{batch['data']['batch_id']}", warden_b)
    assert status == 404
    status, missing_batch = api(client, "get", f"/api/v1/sync/batches/{uuid.uuid4()}", district)
    assert status == 404
    status, audit = api(
        client,
        "get",
        f"/api/v1/audit/?from=2020-01-01T00:00:00Z&to=2099-01-01T00:00:00Z&event_type=report.submitted&aggregate_id={report_id}",
        district,
    )
    assert status == 200
    status, bad_audit = api(client, "get", "/api/v1/audit/?from=yesterday", district)
    assert status == 400
    assert people["admin"]["username"] == "admin"


def test_inbound_handlers_and_engine(client):
    world = make_world()
    admin = login(client, "admin")
    approve_config(client, admin, world["tenant"])
    warden_a = login(client, "warden_a")
    body = report_body(world["shelter_a"], when=_minutes(1), population=10, food=1, water=40, medicine=40)
    assert api(client, "post", "/api/v1/reports/", warden_a, body)[0] == 201
    session = get_session()
    tenant_id = uuid.UUID(world["tenant"])
    vulnerability = {"children": 0, "older_adults": 0, "pregnant_women": 0, "persons_with_disability": 0, "injured_or_sick": 0}
    resources = [
        {"resource_type": "food", "quantity": 40, "unit": "kg"},
        {"resource_type": "water", "quantity": 40, "unit": "l"},
        {"resource_type": "medicine", "quantity": 40, "unit": "kits"},
    ]
    assert ingest(session, tenant_id, "missing", "sms", "m1", _minutes(2).strftime("%Y-%m-%dT%H:%M:%SZ"), 4, vulnerability, resources, "req") is None
    accepted = ingest(session, tenant_id, "111", "telephony", "m2", _minutes(3).strftime("%Y-%m-%dT%H:%M:%SZ"), 4, vulnerability, resources, "req")
    assert accepted["status"] == 201
    drain(session)

    def boom(_session, _envelope):
        raise RuntimeError("handler failed")

    subscribe("coverage.boom", boom)
    publish(
        session,
        event_type="coverage.boom",
        tenant_id=tenant_id,
        actor_id=None,
        aggregate_type="shelter",
        aggregate_id=uuid.UUID(world["shelter_a"]),
        payload={},
        request_id="req",
    )
    drain(session)
    failed = session.query(Outbox).filter(Outbox.event_type == "coverage.boom").one()
    assert failed.attempts == 1 and "handler failed" in failed.last_error

    publish(
        session,
        event_type="shortage.condition_met",
        tenant_id=tenant_id,
        actor_id=None,
        aggregate_type="alert",
        aggregate_id=uuid.uuid4(),
        payload={},
        request_id="req",
    )
    drain(session)
    alert = session.query(Alert).filter(Alert.shelter_id == uuid.UUID(world["shelter_a"]), Alert.resource_type == "food").one()
    session.query(TenantConfiguration).filter(TenantConfiguration.tenant_id == tenant_id).delete()
    session.commit()
    on_shortage(session, {"tenant_id": str(tenant_id), "aggregate_id": str(alert.id), "payload": {}, "event_id": str(uuid.uuid4()), "actor_id": None, "request_id": "req"})
    approve_config(client, admin, world["tenant"])
    session.expire_all()
    ghost_id = uuid.uuid4()
    session.add(
        ResourceSnapshot(
            tenant_id=tenant_id,
            shelter_id=ghost_id,
            report_id=uuid.uuid4(),
            resource_type="food",
            quantity=100,
            unit="kg",
            recorded_at=utcnow(),
        )
    )
    own = session.query(ResourceSnapshot).filter(ResourceSnapshot.shelter_id == uuid.UUID(world["shelter_a"]), ResourceSnapshot.resource_type == "food").one()
    own.quantity = 100
    session.commit()
    envelope = {"tenant_id": str(tenant_id), "aggregate_id": str(alert.id), "payload": {}, "event_id": str(uuid.uuid4()), "actor_id": None, "request_id": "req"}
    on_shortage(session, envelope)
    on_shortage(session, envelope)
    assert on_capacity(session, envelope) is None
    on_sync_batch(session, {"aggregate_id": str(uuid.uuid4()), "tenant_id": str(tenant_id), "payload": {}, "event_id": str(uuid.uuid4()), "request_id": "req"})
    session.close()
    reset_engine()
    assert get_engine() is not None


def test_remaining_branches(client):
    from modules.persistence.tables import ActionRecord
    from modules.schemas.bodies import ResourceListQuery, ShelterUpdate, UserUpdate
    from modules.sync.views import SyncBatchDetailView
    from modules.tenants.views import TenantDetailView

    world = make_world()
    admin = login(client, "admin")
    status, clerk = api(
        client,
        "post",
        "/api/v1/users/",
        admin,
        {"name": "Clerk", "username": "clerk", "password": "password-1", "role": "district_officer", "organization": "District A", "grants": ["user.manage"]},
    )
    assert status == 201
    clerk_token = login(client, "clerk")
    status, missing_config = api(client, "get", f"/api/v1/tenants/{world['tenant']}/configuration", clerk_token)
    assert status == 200 and missing_config["data"]["shortage"] is None
    status, foreign_block = api(client, "post", f"/api/v1/tenants/{world['other']}/blocks", clerk_token, {"name": "Other", "code": "other"})
    assert status == 404
    status, foreign_config = api(client, "put", f"/api/v1/tenants/{world['other']}/configuration", clerk_token, {})
    assert status == 404
    status, foreign_read = api(client, "get", f"/api/v1/tenants/{world['other']}/configuration", clerk_token)
    assert status == 404
    approve_config(client, admin, world["tenant"])
    status, saved_config = api(client, "get", f"/api/v1/tenants/{world['tenant']}/configuration", admin)
    assert status == 200 and saved_config["data"]["shortage"]["food"]["unit"] == "kg"
    status, east_block = api(client, "post", f"/api/v1/tenants/{world['tenant']}/blocks", admin, {"name": "East", "code": "east"})
    assert status == 201
    people = _users(client, admin)
    status, _officer = api(
        client,
        "post",
        "/api/v1/users/",
        admin,
        {"name": "East Officer", "username": "east", "password": "password-1", "role": "block_officer", "organization": "District A", "block_id": east_block["data"]["id"]},
    )
    assert status == 201
    status, _trainer = api(
        client,
        "post",
        "/api/v1/users/",
        admin,
        {"name": "Trainer", "username": "trainer", "password": "password-1", "role": "volunteer", "organization": "District A", "block_id": world["block"], "support_functions": ["training"]},
    )
    assert status == 201
    trainer = login(client, "trainer")
    status, trainer_shelters = api(client, "get", "/api/v1/shelters/", trainer)
    assert status == 200 and trainer_shelters["data"]
    warden = login(client, "warden_a")
    status, own_shelters = api(client, "get", "/api/v1/shelters/", warden)
    assert status == 200 and len(own_shelters["data"]) == 1
    status, attention = api(client, "post", "/api/v1/reports/", warden, report_body(world["shelter_a"], when=_minutes(1), population=10, food=10, water=40, medicine=40))
    assert status == 201
    district = login(client, "district")
    status, dashboard = api(client, "get", "/api/v1/dashboard/shelters", district)
    assert status == 200 and any(row["priority_factors"]["shortage_urgency"] == "attention" for row in dashboard["data"])
    block = login(client, "block")
    status, block_rows = api(client, "get", f"/api/v1/dashboard/shelters?block_id={world['block']}", block)
    assert status == 200 and block_rows["data"]
    east = login(client, "east")
    status, east_resources = api(client, "get", "/api/v1/resources/?resource_type=food", east)
    assert status == 200 and east_resources["data"] == []
    status, east_actions = api(client, "get", "/api/v1/actions/?decision=approved", east)
    assert status == 200 and east_actions["data"] == []
    status, east_summary = api(client, "get", "/api/v1/dashboard/summary", east)
    assert status == 200
    status, shelter = api(
        client,
        "post",
        "/api/v1/shelters/",
        admin,
        {"name": "Shelter C", "block_id": east_block["data"]["id"], "location_label": "East", "capacity": 20, "warden_user_id": people["warden_a"]["id"], "reporting_contact": "444"},
    )
    assert status == 201
    status, bad_warden = api(client, "patch", f"/api/v1/shelters/{world['shelter_a']}", district, {"warden_user_id": people["district"]["id"]})
    assert status == 404
    status, granted = api(client, "patch", f"/api/v1/users/{clerk['data']['id']}", admin, {"grants": ["user.manage"], "role": "district_officer"})
    assert status == 200 and granted["data"]["grants"] == ["user.manage"]
    status, empty_user = api(client, "patch", f"/api/v1/users/{clerk['data']['id']}", admin, {})
    assert status == 400
    status, users = api(client, "get", f"/api/v1/users/?shelter_id={world['shelter_a']}&page_size=100", admin)
    assert status == 200 and users["meta"]["total"] >= 1
    warden_login = api(client, "post", "/api/v1/auth/login", body={"username": "warden_b", "password": "password-1"})
    assert warden_login[0] == 200
    session = get_session()
    inactive_user = session.query(User).filter(User.username == "warden_b").one()
    inactive_user.status = "inactive"
    session.commit()
    session.close()
    status, inactive_refresh = api(client, "post", "/api/v1/auth/refresh", body={"refresh_token": warden_login[1]["data"]["refresh_token"]})
    assert status == 401
    status, missing_transition = api(client, "post", f"/api/v1/alerts/{uuid.uuid4()}/acknowledge", district, {})
    assert status == 404
    with pytest.raises(ValueError):
        ShelterCreate(
            name="A",
            block_id=world["block"],
            location_label="Here",
            latitude=10,
            longitude=200,
            capacity=1,
            warden_user_id=people["warden_a"]["id"],
            reporting_contact="1",
        )
    with pytest.raises(ValueError):
        UserUpdate.model_validate({})
    assert ShelterUpdate(name="Named").name == "Named"
    assert ResourceListQuery.model_validate({"surplus": True}).surplus is True
    assert ResourceListQuery.model_validate({"surplus": False}).surplus is False
    assert ResourceListQuery.model_validate({"surplus": ""}).surplus is None
    assert ResourceListQuery.model_validate({"surplus": "true"}).surplus is True

    session = get_session()
    shelter_row = session.get(Shelter, uuid.UUID(world["shelter_a"]))
    warden_principal = Principal(uuid.uuid4(), shelter_row.tenant_id, "warden", None, shelter_row.block_id, {"report.submit"}, [])
    with pytest.raises(ApiError) as mismatch:
        submit(session, warden_principal, ReportCreate.model_validate(report_body(world["shelter_a"], when=_minutes(2))), "req")
    assert mismatch.value.status == 404
    alert = session.query(Alert).filter(Alert.shelter_id == shelter_row.id).first()
    other = session.get(Shelter, uuid.UUID(world["shelter_b"]))
    snap = session.query(ResourceSnapshot).filter(ResourceSnapshot.shelter_id == other.id, ResourceSnapshot.resource_type == "food").one_or_none()
    if snap is None:
        session.add(
            ResourceSnapshot(
                tenant_id=shelter_row.tenant_id,
                shelter_id=other.id,
                report_id=uuid.uuid4(),
                resource_type="food",
                quantity=80,
                unit="kg",
                recorded_at=utcnow(),
            )
        )
    else:
        snap.quantity = 80
    session.commit()
    envelope = {"tenant_id": str(shelter_row.tenant_id), "aggregate_id": str(alert.id), "payload": {}, "event_id": str(uuid.uuid4()), "actor_id": None, "request_id": "req"}
    on_shortage(session, {"tenant_id": str(shelter_row.tenant_id), "aggregate_id": str(uuid.uuid4()), "payload": {}, "event_id": str(uuid.uuid4()), "actor_id": None, "request_id": "req"})
    on_shortage(session, envelope)
    on_shortage(session, envelope)
    action = session.query(ActionRecord).filter(ActionRecord.destination_shelter_id == shelter_row.id).first()
    session.add(
        ActionRecord(
            tenant_id=shelter_row.tenant_id,
            alert_id=alert.id,
            source_shelter_id=other.id,
            destination_shelter_id=uuid.UUID(shelter["data"]["id"]),
            resource_type="food",
            suggested_quantity=1,
            decision="proposed",
            status="proposed",
            explanation_key="action.explanation",
            explanation_params={},
        )
    )
    session.commit()
    action_id = action.id
    session.close()
    status, outside = api(client, "get", "/api/v1/dashboard/summary", block)
    assert status == 200
    status, hidden_actions = api(client, "get", "/api/v1/actions/", east)
    assert status == 200
    status, hidden_summary = api(client, "get", "/api/v1/dashboard/summary", east)
    assert status == 200 and hidden_summary["data"]["unresolved_action_count"] >= 0
    status, proposed = api(client, "get", "/api/v1/actions/?decision=rejected", district)
    assert status == 200
    status, by_shelter = api(client, "get", f"/api/v1/actions/?shelter_id={shelter['data']['id']}", district)
    assert status == 200
    status, by_block = api(client, "get", f"/api/v1/actions/?block_id={east_block['data']['id']}", district)
    assert status == 200 and by_block["meta"]["total"] >= 1
    status, visible_action = api(client, "get", f"/api/v1/actions/{action_id}", block)
    assert status == 200
    anonymous = RequestFactory().get("/api/v1/sync/batches/" + str(uuid.uuid4()))
    anonymous.principal = Principal(uuid.uuid4(), uuid.UUID(world["tenant"]), "volunteer", None, None, set(), [])
    anonymous.db = get_session()
    anonymous.request_id = "req"
    assert SyncBatchDetailView.as_view()(anonymous, batch_id=uuid.uuid4()).status_code == 403
    anonymous.db.close()
    tenant_request = RequestFactory().get(f"/api/v1/tenants/{world['tenant']}")
    tenant_request.principal = None
    tenant_request.request_id = "req"
    tenant_request.db = get_session()
    assert TenantDetailView.as_view()(tenant_request, tenant_id=uuid.UUID(world["tenant"])).status_code == 401
    tenant_request.db.close()
    assert outside["data"]["unresolved_action_count"] >= 0
    assert proposed["meta"]["total"] >= 0
    assert by_shelter["meta"]["total"] >= 1


def test_schema_objects_cover_remaining_validators():
    with pytest.raises(ValueError):
        UserCreate(name="A", username="a", password="password-1", role="block_officer", organization="Org", shelter_id=str(uuid.uuid4()))
    with pytest.raises(ValueError):
        UserCreate(name="A", username="a", password="password-1", role="district_officer", organization="Org", block_id=str(uuid.uuid4()))
    with pytest.raises(ValueError):
        UserCreate(name="A", username="a", password="password-1", role="volunteer", organization="Org", support_functions=["training"], grants=["user.manage"])
    with pytest.raises(ValueError):
        ShelterCreate(
            name="A",
            block_id=str(uuid.uuid4()),
            location_label="Here",
            latitude=None,
            longitude=10,
            capacity=1,
            warden_user_id=str(uuid.uuid4()),
            reporting_contact="1",
        )
    with pytest.raises(ValueError):
        ConfigurationBody.model_validate({"capacity": {"attention_at_ratio": 0.9, "urgent_at_ratio": 0.2}})
