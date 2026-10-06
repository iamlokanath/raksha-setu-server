import uuid

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Uuid


class Base(DeclarativeBase):
    pass


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class Identified:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_id)
