import pytest
from pydantic import ValidationError

from app.config import Settings


def test_secret_key_must_be_long_enough() -> None:
    with pytest.raises(ValidationError):
        Settings(DATABASE_URL="postgresql+psycopg://x@y/z", RUNPAD_SECRET_KEY="short")
