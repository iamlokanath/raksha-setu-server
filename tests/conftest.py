import json
import os
import uuid
from datetime import timedelta

import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "raksha.settings")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-with-32-bytes-min"
os.environ["ACCESS_TOKEN_TTL_SECONDS"] = "900"
os.environ["REFRESH_TOKEN_TTL_SECONDS"] = "604800"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000"

django.setup()

from django.test import Client

from common.authz.passwords import hash_password
from common.db.base import Base
from common.db.session import get_engine, get_session
from common.timeutil import utcnow
from modules.persistence.tables import Assignment, Block, Shelter, Tenant, TenantConfiguration, User


@pytest.fixture(autouse=True)
def fresh_database():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    return Client()


def api(client, method, path, token=None, body=None):
    headers = {}
    if token:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body)
    response = getattr(client, method)(path, data=data, content_type="application/json", **headers)
    payload = json.loads(response.content) if response.content else None
    return response.status_code, payload


def make_world():
    session = get_session()
    tenant = Tenant(name="District A", code="a", status="active")
    other = Tenant(name="District B", code="b", status="active")
    session.add_all([tenant, other])
    session.flush()
    block = Block(tenant_id=tenant.id, name="Block 1", code="b1")
    session.add(block)
    session.flush()
    password = hash_password("password-1")

    def user(name, username, role, grants=None):
        row = User(
            tenant_id=tenant.id,
            name=name,
            username=username,
            role=role,
            organization="District A",
            password_hash=password,
            grants=grants or [],
            status="active",
        )
        session.add(row)
        session.flush()
        return row

    admin = user("Admin", "admin", "district_officer", ["shelter.register", "user.manage", "tenant.manage"])
    district = user("District", "district", "district_officer")
    block_officer = user("Block", "block", "block_officer")
    warden_a = user("Warden A", "warden_a", "warden")
    warden_b = user("Warden B", "warden_b", "warden")
    outsider = User(
        tenant_id=other.id,
        name="Outsider",
        username="outsider",
        role="district_officer",
        organization="District B",
        password_hash=password,
        grants=[],
        status="active",
    )
    session.add(outsider)
    session.flush()
    shelter_a = Shelter(
        tenant_id=tenant.id,
        block_id=block.id,
        name="Shelter A",
        location_label="North",
        capacity=100,
        warden_user_id=warden_a.id,
        reporting_contact="111",
        operational_status="active",
        current_status="unknown",
    )
    shelter_b = Shelter(
        tenant_id=tenant.id,
        block_id=block.id,
        name="Shelter B",
        location_label="South",
        capacity=80,
        warden_user_id=warden_b.id,
        reporting_contact="222",
        operational_status="active",
        current_status="unknown",
    )
    session.add_all([shelter_a, shelter_b])
    session.flush()
    for person, shelter_id, block_id in (
        (admin, None, None),
        (district, None, None),
        (block_officer, None, block.id),
        (warden_a, shelter_a.id, None),
        (warden_b, shelter_b.id, None),
        (outsider, None, None),
    ):
        session.add(Assignment(tenant_id=person.tenant_id, user_id=person.id, shelter_id=shelter_id, block_id=block_id, support_functions=[]))
    session.commit()
    ids = {
        "tenant": str(tenant.id),
        "other": str(other.id),
        "block": str(block.id),
        "shelter_a": str(shelter_a.id),
        "shelter_b": str(shelter_b.id),
    }
    session.close()
    return ids


def login(client, username="district"):
    status, body = api(client, "post", "/api/v1/auth/login", body={"username": username, "password": "password-1"})
    assert status == 200, body
    return body["data"]["access_token"]


def report_body(shelter_id, population=10, food=20, water=20, medicine=20, when=None):
    return {
        "client_report_id": str(uuid.uuid4()),
        "shelter_id": shelter_id,
        "reported_at": (when or utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "population": population,
        "vulnerability": {
            "children": 1,
            "older_adults": 1,
            "pregnant_women": 0,
            "persons_with_disability": 0,
            "injured_or_sick": 0,
        },
        "resources": [
            {"resource_type": "food", "quantity": food, "unit": "kg"},
            {"resource_type": "water", "quantity": water, "unit": "l"},
            {"resource_type": "medicine", "quantity": medicine, "unit": "kits"},
        ],
        "incident_notes": "",
        "channel": "web",
    }


def approve_config(client, token, tenant_id):
    body = {
        "shortage": {
            "food": {"attention_below": 15, "urgent_below": 5, "surplus_above": 30, "unit": "kg"},
            "water": {"attention_below": 15, "urgent_below": 5, "surplus_above": 30, "unit": "l"},
            "medicine": {"attention_below": 15, "urgent_below": 5, "surplus_above": 30, "unit": "kits"},
        },
        "capacity": {"attention_at_ratio": 0.8, "urgent_at_ratio": 1.0},
        "priority": {
            "weights": {
                "shortage_urgency": 0.4,
                "vulnerable_population": 0.2,
                "occupancy_pressure": 0.2,
                "issue_age": 0.2,
            },
            "vulnerable_cap": 50,
            "age_cap_hours": 48,
            "severity_scores": {"none": 0, "attention": 0.5, "urgent": 1},
            "bands": {"high": 0.6, "medium": 0.3},
        },
    }
    status, payload = api(client, "put", f"/api/v1/tenants/{tenant_id}/configuration", token, body)
    assert status == 200, payload
    return body
