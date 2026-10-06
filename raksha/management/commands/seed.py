import os

from django.core.management.base import BaseCommand

from common.authz.passwords import hash_password
from common.db.base import Base
from common.db.session import get_engine, get_session
from modules.persistence.tables import Assignment, Block, Shelter, Tenant, User


class Command(BaseCommand):
    help = "Create the pilot district, block, shelters, and users. Password comes from SEED_PASSWORD."

    def handle(self, *args, **options):
        password = os.environ.get("SEED_PASSWORD", "")
        if len(password) < 8:
            self.stderr.write("Set SEED_PASSWORD to at least 8 characters before seeding.")
            return
        Base.metadata.create_all(get_engine())
        session = get_session()
        if session.query(Tenant).filter(Tenant.code == "pilot").first():
            self.stdout.write("Pilot data already exists.")
            session.close()
            return
        tenant = Tenant(name="Pilot District", code="pilot", status="active")
        session.add(tenant)
        session.flush()
        block = Block(tenant_id=tenant.id, name="Pilot Block", code="pilot-block")
        session.add(block)
        session.flush()
        users = {}
        specs = [
            ("admin", "Pilot Administrator", "district_officer", ["shelter.register", "user.manage", "tenant.manage"]),
            ("district", "District Officer", "district_officer", []),
            ("block", "Block Officer", "block_officer", []),
            ("warden_a", "Warden A", "warden", []),
            ("warden_b", "Warden B", "warden", []),
            ("volunteer", "Support Volunteer", "volunteer", []),
        ]
        for username, name, role, grants in specs:
            user = User(
                tenant_id=tenant.id,
                name=name,
                username=username,
                role=role,
                organization="Pilot District",
                status="active",
                password_hash=hash_password(password),
                grants=grants,
            )
            session.add(user)
            session.flush()
            users[username] = user
        shelter_a = Shelter(
            tenant_id=tenant.id,
            block_id=block.id,
            name="Shelter A",
            location_label="Pilot Block, north school",
            capacity=100,
            warden_user_id=users["warden_a"].id,
            reporting_contact="9000000001",
            operational_status="active",
            current_status="unknown",
        )
        shelter_b = Shelter(
            tenant_id=tenant.id,
            block_id=block.id,
            name="Shelter B",
            location_label="Pilot Block, south school",
            capacity=80,
            warden_user_id=users["warden_b"].id,
            reporting_contact="9000000002",
            operational_status="active",
            current_status="unknown",
        )
        session.add_all([shelter_a, shelter_b])
        session.flush()
        assignments = [
            (users["admin"], None, None, []),
            (users["district"], None, None, []),
            (users["block"], None, block.id, []),
            (users["warden_a"], shelter_a.id, None, []),
            (users["warden_b"], shelter_b.id, None, []),
            (users["volunteer"], shelter_a.id, None, ["reporting_support", "training"]),
        ]
        for user, shelter_id, block_id, support in assignments:
            session.add(
                Assignment(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    shelter_id=shelter_id,
                    block_id=block_id,
                    support_functions=support,
                )
            )
        session.commit()
        session.close()
        self.stdout.write("Pilot district, block, two shelters, and users are ready.")
