import uuid
from datetime import timedelta

from common.timeutil import utcnow
from modules.persistence.tables import AuditEvent, Outbox, Shelter
from tests.conftest import api, approve_config, login, make_world, report_body


def test_ac_001_shelter_registration(client):
    world = make_world()
    token = login(client, "admin")
    status, body = api(
        client,
        "post",
        "/api/v1/shelters/",
        token,
        {
            "name": "Shelter C",
            "block_id": world["block"],
            "location_label": "East school",
            "capacity": 40,
            "warden_user_id": _user_id(client, token, "warden_a"),
            "reporting_contact": "333",
            "operational_status": "active",
        },
    )
    assert status == 201, body
    detail, payload = api(client, "get", f"/api/v1/shelters/{body['data']['id']}", token)
    assert detail == 200
    for field in ("name", "location_label", "capacity", "warden_user_id", "reporting_contact", "operational_status"):
        assert payload["data"][field]


def test_ac_002_and_validation(client):
    world = make_world()
    token = login(client, "warden_a")
    body = report_body(world["shelter_a"])
    status, payload = api(client, "post", "/api/v1/reports/", token, body)
    assert status == 201, payload
    assert payload["data"]["reported_at"]
    bad = report_body(world["shelter_a"], population=1)
    bad["vulnerability"]["children"] = 2
    status, payload = api(client, "post", "/api/v1/reports/", token, bad)
    assert status == 400
    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_idempotent_and_stale_report(client):
    world = make_world()
    token = login(client, "warden_a")
    first = report_body(world["shelter_a"], food=9, when=utcnow())
    status, _ = api(client, "post", "/api/v1/reports/", token, first)
    assert status == 201
    status, replay = api(client, "post", "/api/v1/reports/", token, first)
    assert status == 200
    assert replay["meta"]["idempotent_replay"] is True
    first["resources"][0]["quantity"] = 1
    status, mismatch = api(client, "post", "/api/v1/reports/", token, first)
    assert status == 409
    assert mismatch["error"]["code"] == "DUPLICATE_MISMATCH"
    older = report_body(world["shelter_a"], food=1, when=utcnow() - timedelta(hours=2))
    status, historical = api(client, "post", "/api/v1/reports/", token, older)
    assert status == 201
    assert historical["data"]["applied_to_current"] is False
    resources, stock = api(client, "get", f"/api/v1/shelters/{world['shelter_a']}/resources", token)
    assert resources == 200
    food = next(item for item in stock["data"] if item["resource_type"] == "food")
    assert food["quantity"] == 9


def test_ac_003_sync_batch(client):
    world = make_world()
    token = login(client, "warden_a")
    newer = report_body(world["shelter_a"], food=12, when=utcnow())
    older = report_body(world["shelter_a"], food=3, when=utcnow() - timedelta(days=1))
    status, payload = api(client, "post", "/api/v1/sync/reports", token, {"reports": [newer, older, newer]})
    assert status == 202, payload
    status, batch = api(client, "get", f"/api/v1/sync/batches/{payload['data']['batch_id']}", token)
    assert status == 200
    states = [item["state"] for item in batch["data"]["items"]]
    assert states.count("applied") == 1
    assert "stored_historical" in states
    assert "duplicate" in states
    resources, stock = api(client, "get", f"/api/v1/shelters/{world['shelter_a']}/resources", token)
    food = next(item for item in stock["data"] if item["resource_type"] == "food")
    assert food["quantity"] == 12


def test_ac_004_008_alerts_need_configuration(client):
    world = make_world()
    admin = login(client, "admin")
    district = login(client, "district")
    warden = login(client, "warden_a")
    status, _ = api(client, "post", "/api/v1/reports/", warden, report_body(world["shelter_a"], food=1, population=10))
    assert status == 201
    status, alerts = api(client, "get", "/api/v1/alerts/", district)
    assert alerts["data"] == []
    approve_config(client, admin, world["tenant"])
    status, created = api(client, "post", "/api/v1/reports/", warden, report_body(world["shelter_a"], food=1, population=100))
    assert status == 201, created
    status, alerts = api(client, "get", "/api/v1/alerts/?type=shortage", district)
    shortage = next(item for item in alerts["data"] if item["resource_type"] == "food")
    assert shortage["status"] == "detected"
    assert shortage["severity"] == "urgent"
    steps = ["acknowledge", "plan", "start", "resolve", "close"]
    current = shortage["id"]
    for step in steps:
        status, body = api(client, "post", f"/api/v1/alerts/{current}/{step}", district, {})
        assert status == 200, body
    status, illegal = api(client, "post", f"/api/v1/alerts/{current}/acknowledge", district, {})
    assert status == 422
    assert illegal["error"]["code"] == "INVALID_STATE"


def test_ac_005_006_007_009(client):
    world = make_world()
    admin = login(client, "admin")
    district = login(client, "district")
    approve_config(client, admin, world["tenant"])
    api(client, "post", "/api/v1/reports/", login(client, "warden_b"), report_body(world["shelter_b"], food=40, population=10))
    api(client, "post", "/api/v1/reports/", login(client, "warden_a"), report_body(world["shelter_a"], food=1, population=90))
    status, actions = api(client, "get", "/api/v1/actions/?decision=proposed", district)
    assert status == 200
    match = next(item for item in actions["data"] if item["destination_shelter_id"] == world["shelter_a"])
    assert match["source_shelter_id"] == world["shelter_b"]
    assert match["explanation_key"] == "action.explanation"
    status, denied = api(client, "post", f"/api/v1/actions/{match['id']}/confirm-receipt", login(client, "warden_a"), {"quantity": 1, "unit": "kg"})
    assert status == 422
    assert denied["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"
    status, blocked = api(client, "post", f"/api/v1/actions/{match['id']}/approve", login(client, "block"), {})
    assert status == 403
    status, approved = api(client, "post", f"/api/v1/actions/{match['id']}/approve", district, {})
    assert status == 200
    assert approved["data"]["decision"] == "approved"
    status, summary = api(client, "get", "/api/v1/dashboard/summary", district)
    assert summary["data"]["urgent_shelter_count"] >= 1
    assert summary["data"]["surplus_shelter_count"] >= 1
    status, shelters = api(client, "get", "/api/v1/dashboard/shelters", district)
    factors = shelters["data"][0]["priority_factors"]
    for key in ("shortage_urgency", "vulnerable_population", "occupancy_pressure", "issue_age_seconds"):
        assert key in factors
    assert shelters["data"][0]["priority_score"] is not None


def test_priority_without_configuration_is_null(client):
    world = make_world()
    district = login(client, "district")
    api(client, "post", "/api/v1/reports/", login(client, "warden_a"), report_body(world["shelter_a"]))
    status, shelters = api(client, "get", "/api/v1/dashboard/shelters", district)
    assert shelters["data"][0]["priority_score"] is None
    assert shelters["data"][0]["priority_factors"]["vulnerable_population"] == 2
    status, filtered = api(client, "get", "/api/v1/dashboard/shelters?priority=high", district)
    assert status == 422
    assert filtered["error"]["code"] == "CONFIGURATION_REQUIRED"


def test_ac_010_audit_and_security(client):
    world = make_world()
    district = login(client, "district")
    warden = login(client, "warden_a")
    api(client, "post", "/api/v1/reports/", warden, report_body(world["shelter_a"]))
    status, audit = api(client, "get", "/api/v1/audit/?event_type=report.submitted", district)
    assert status == 200
    assert audit["data"]
    status, denied = api(client, "get", "/api/v1/audit/", login(client, "block"))
    assert status == 403
    status, missing = api(client, "get", "/api/v1/shelters/", None)
    assert status == 401
    outsider = login(client, "outsider")
    status, hidden = api(client, "get", f"/api/v1/shelters/{world['shelter_a']}", outsider)
    assert status == 404
    status, bad = api(client, "post", "/api/v1/auth/login", body={"username": "warden_a", "password": "nope"})
    assert status == 401
    status, extra = api(client, "post", "/api/v1/reports/", warden, {**report_body(world["shelter_a"]), "extra": True})
    assert status == 400
    assert extra["error"]["code"] == "VALIDATION_ERROR"


def test_get_does_not_emit_domain_events(client):
    world = make_world()
    token = login(client, "district")
    from common.db.session import get_session

    session = get_session()
    before = session.query(Outbox).count()
    session.close()
    api(client, "get", "/api/v1/dashboard/shelters", token)
    session = get_session()
    after = session.query(Outbox).count()
    session.close()
    assert after == before
    assert world["tenant"]


def test_unreported_is_not_zero(client):
    world = make_world()
    token = login(client, "warden_a")
    status, body = api(client, "get", f"/api/v1/shelters/{world['shelter_a']}/resources", token)
    assert status == 200
    assert all(item["quantity"] is None and item["status"] == "unreported" for item in body["data"])


def _user_id(client, token, username):
    status, body = api(client, "get", "/api/v1/users/?role=warden", token)
    assert status == 200
    return next(item["id"] for item in body["data"] if item["username"] == username)
