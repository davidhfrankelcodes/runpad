"""SSH connections to Targets: host key scanning, pinned connections, and connection tests.

Host keys are pinned: a connection only succeeds if the server presents exactly the key
recorded when the Target was created. Nothing is read from ~/.ssh.
"""

import asyncio
import base64
import binascii
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncssh

CONNECT_TIMEOUT_SECONDS = 10
# When scanning, ask for the strongest key the server has, so that is the one pinned.
HOST_KEY_PREFERENCE = [
    "ssh-ed25519",
    "ecdsa-sha2-nistp521",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp256",
    "rsa-sha2-512",
    "rsa-sha2-256",
    "ssh-rsa",
]


class SshKeyError(ValueError):
    """A private or public key could not be parsed."""


@dataclass(frozen=True)
class HostKey:
    public_key: str  # One OpenSSH line: "<algorithm> <base64>"
    algorithm: str
    fingerprint: str  # "SHA256:..."


@dataclass(frozen=True)
class SshEndpoint:
    host: str
    port: int
    username: str
    host_key: str
    private_key: str


@dataclass(frozen=True)
class ConnectionCheck:
    ok: bool
    message: str


def generate_private_key() -> str:
    key = asyncssh.generate_private_key("ssh-ed25519", comment="runpad")
    return key.export_private_key("openssh").decode()


_OPENSSH_HEADER = "-----BEGIN OPENSSH PRIVATE KEY-----"
_OPENSSH_MAGIC = b"openssh-key-v1\0"


def _is_passphrase_protected(value: str) -> bool:
    if "Proc-Type: 4,ENCRYPTED" in value or "BEGIN ENCRYPTED PRIVATE KEY" in value:
        return True
    if _OPENSSH_HEADER not in value:
        return False
    body = "".join(line for line in value.strip().splitlines() if not line.startswith("-----"))
    try:
        blob = base64.b64decode(body)
    except (binascii.Error, ValueError):
        return False
    if not blob.startswith(_OPENSSH_MAGIC):
        return False
    # Format: magic, then a length-prefixed cipher name ("none" when unencrypted).
    offset = len(_OPENSSH_MAGIC)
    length = int.from_bytes(blob[offset : offset + 4], "big")
    return blob[offset + 4 : offset + 4 + length] != b"none"


def load_private_key(value: str) -> asyncssh.SSHKey:
    if _is_passphrase_protected(value):
        raise SshKeyError(
            "Passphrase-protected keys are not supported. Remove the passphrase from a copy "
            "of the key (ssh-keygen -p), or generate a key in runpad instead."
        )
    try:
        return asyncssh.import_private_key(value.strip() + "\n")
    except (asyncssh.KeyImportError, ValueError) as exc:
        raise SshKeyError("Not a valid private key (OpenSSH or PEM format)") from exc


def public_key_of(private_key: str) -> str:
    """The OpenSSH public key line for authorized_keys, with a "runpad" comment."""
    exported = load_private_key(private_key).export_public_key("openssh").decode()
    algorithm, blob = exported.split()[:2]
    return f"{algorithm} {blob} runpad"


def normalize_private_key(value: str) -> str:
    return load_private_key(value).export_private_key("openssh").decode()


def parse_host_key(value: str) -> HostKey:
    try:
        key = asyncssh.import_public_key(value.strip())
    except (asyncssh.KeyImportError, ValueError) as exc:
        raise SshKeyError("Not a valid SSH public key") from exc
    return _host_key(key)


def _host_key(key: asyncssh.SSHKey) -> HostKey:
    algorithm, blob = key.export_public_key("openssh").decode().split()[:2]
    return HostKey(
        public_key=f"{algorithm} {blob}",
        algorithm=algorithm,
        fingerprint=key.get_fingerprint("sha256"),
    )


async def scan_host_key(host: str, port: int) -> HostKey:
    """Fetch the server's host key so an admin can confirm and pin it."""
    async with asyncio.timeout(CONNECT_TIMEOUT_SECONDS):
        key = await asyncssh.get_server_host_key(
            host, port, server_host_key_algs=HOST_KEY_PREFERENCE
        )
    if key is None:
        raise ConnectionError("Server did not present a host key")
    return _host_key(key)


@asynccontextmanager
async def connect(endpoint: SshEndpoint) -> AsyncIterator[asyncssh.SSHClientConnection]:
    """Open a connection that only trusts the pinned host key and the stored client key."""
    pinned = asyncssh.import_public_key(endpoint.host_key)
    async with asyncssh.connect(
        endpoint.host,
        port=endpoint.port,
        username=endpoint.username,
        client_keys=[load_private_key(endpoint.private_key)],
        known_hosts=([pinned], [], []),
        preferred_auth="publickey",
        agent_path=None,
        config=[],
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        login_timeout=CONNECT_TIMEOUT_SECONDS,
    ) as conn:
        yield conn


async def check_connection(endpoint: SshEndpoint) -> ConnectionCheck:
    """Connect and authenticate without running any command."""
    try:
        async with connect(endpoint):
            pass
    except asyncssh.HostKeyNotVerifiable:
        return ConnectionCheck(
            ok=False,
            message="Host key does not match the pinned key. If the host was reinstalled, "
            "re-scan and re-pin the key.",
        )
    except asyncssh.PermissionDenied:
        return ConnectionCheck(
            ok=False,
            message=f"Authentication failed for user {endpoint.username!r}. Is the public key "
            "in authorized_keys?",
        )
    except (OSError, TimeoutError, asyncssh.Error) as exc:
        return ConnectionCheck(ok=False, message=f"Could not connect: {exc}")
    return ConnectionCheck(ok=True, message="Connected and authenticated")
