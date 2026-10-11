import enum

from sqlalchemy import LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel, enum_check, str_enum


class SecretKind(enum.StrEnum):
    SSH_KEY = "ssh_key"
    TEXT = "text"


class Secret(TimestampedModel):
    """An encrypted value. The plaintext never leaves the server after creation."""

    __tablename__ = "secrets"
    __table_args__ = (enum_check("kind", SecretKind),)

    name: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[SecretKind] = mapped_column(str_enum(SecretKind))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Format and key derivation: see security.SecretCipher.
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    # For ssh_key secrets: the OpenSSH public key, safe to show and copy.
    public_key: Mapped[str | None] = mapped_column(Text)
