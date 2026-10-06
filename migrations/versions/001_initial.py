"""Initial schema."""

from alembic import op

from common.db.base import Base
from common.persistence import ensure_models

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    ensure_models()
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    ensure_models()
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
