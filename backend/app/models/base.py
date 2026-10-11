import enum
import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import CheckConstraint, DateTime, Enum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampedModel(Base):
    """UUID primary key plus UTC created_at and updated_at, required on every table."""

    __abstract__ = True
    # Load server-generated columns (updated_at) via RETURNING, so they never lazy-load later.
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def str_enum(enum_cls: type[enum.StrEnum]) -> Enum:
    """A StrEnum stored as VARCHAR. Pair with enum_check() in __table_args__."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=16,
        values_callable=lambda e: [m.value for m in e],
    )


def enum_check(column: str, enum_cls: type[enum.StrEnum]) -> CheckConstraint:
    """CHECK that a str_enum column holds a valid value. Named ck_<table>_<column>.

    Declared explicitly (rather than Enum(create_constraint=True)) because Alembic
    autogenerate renders the implicit constraint twice.
    """
    values = ", ".join(f"'{m.value}'" for m in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=column)
