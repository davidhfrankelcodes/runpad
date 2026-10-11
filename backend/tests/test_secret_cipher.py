import uuid

import pytest

from app.security import SecretCipher, SecretDecryptionError

KEY = "k" * 64


def test_round_trip() -> None:
    cipher = SecretCipher(KEY)
    row = uuid.uuid4()
    assert cipher.decrypt(cipher.encrypt("hunter2", row), row) == "hunter2"


def test_ciphertext_hides_plaintext_and_uses_fresh_nonces() -> None:
    cipher = SecretCipher(KEY)
    row = uuid.uuid4()
    first, second = cipher.encrypt("hunter2", row), cipher.encrypt("hunter2", row)
    assert b"hunter2" not in first
    assert first != second


def test_ciphertext_is_bound_to_its_row() -> None:
    cipher = SecretCipher(KEY)
    blob = cipher.encrypt("hunter2", uuid.uuid4())
    with pytest.raises(SecretDecryptionError):
        cipher.decrypt(blob, uuid.uuid4())


def test_changed_secret_key_cannot_decrypt() -> None:
    row = uuid.uuid4()
    blob = SecretCipher(KEY).encrypt("hunter2", row)
    with pytest.raises(SecretDecryptionError):
        SecretCipher("z" * 64).decrypt(blob, row)


def test_tampered_ciphertext_is_rejected() -> None:
    cipher = SecretCipher(KEY)
    row = uuid.uuid4()
    blob = bytearray(cipher.encrypt("hunter2", row))
    blob[-1] ^= 1
    with pytest.raises(SecretDecryptionError):
        cipher.decrypt(bytes(blob), row)
