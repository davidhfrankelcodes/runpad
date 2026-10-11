"""SSH connections to Targets: host key scanning, pinned connections, and connection tests.

Host keys are pinned: a connection only succeeds if the server presents exactly the key
recorded when the Target was created. Nothing is read from ~/.ssh.
"""

import asyncio
import base64
import binascii
import contextlib
import shlex
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncssh

from app.executors.base import (
    ConnectionCheck,
    ExecutionError,
    ExecutionRequest,
    OutputCallback,
    SshEndpoint,
)

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


def describe_error(exc: BaseException, endpoint: SshEndpoint) -> str:
    """A message an admin can act on, for a failed connection."""
    if isinstance(exc, asyncssh.HostKeyNotVerifiable):
        return (
            "Host key does not match the pinned key. If the host was reinstalled, "
            "re-scan and re-pin the key."
        )
    if isinstance(exc, asyncssh.PermissionDenied):
        return (
            f"Authentication failed for user {endpoint.username!r}. "
            "Is the public key in authorized_keys?"
        )
    return f"Could not connect: {exc}"


_CONNECT_ERRORS = (OSError, TimeoutError, asyncssh.Error)


async def check_connection(endpoint: SshEndpoint) -> ConnectionCheck:
    """Connect and authenticate without running any command."""
    try:
        async with connect(endpoint):
            pass
    except _CONNECT_ERRORS as exc:
        return ConnectionCheck(ok=False, message=describe_error(exc, endpoint))
    return ConnectionCheck(ok=True, message="Connected and authenticated")


# --- Executor --------------------------------------------------------------

# The only command line runpad sends. It contains nothing from the Action or the user:
# the payload (arguments, secret variables, script) arrives on stdin, so none of it shows
# in the remote process list. $1 is the payload length in bytes.
#
# The script runs in its own session (setsid, where available) with stdin from /dev/null.
# The wrapper's stdin stays open as a lifeline (kept on fd 3, because background jobs
# otherwise get /dev/null): when runpad closes it (cancel, timeout, or a dropped
# connection) the watcher kills the script's whole process group. When the script exits
# normally, anything it left running in the background is killed too.
REMOTE_WRAPPER = r"""
exec 3<&0
p=$(head -c "$1" <&3)
if command -v setsid >/dev/null 2>&1; then s=setsid; else s=; fi
P="$p" $s sh -c 'p=$P; unset P; eval "$p"' </dev/null &
c=$!
{
  cat <&3 >/dev/null
  kill -TERM -"$c" "$c" 2>/dev/null
  sleep 3
  kill -KILL -"$c" "$c" 2>/dev/null
} >/dev/null 2>&1 &
w=$!
wait "$c"
r=$?
kill -KILL -"$c" 2>/dev/null
kill "$w" 2>/dev/null
exit "$r"
""".strip()

EXIT_GRACE_SECONDS = 5
READ_SIZE = 4096


def build_payload(request: ExecutionRequest) -> bytes:
    """Shell text that sets positional parameters and variables, then runs the script.

    Every value is single-quoted with shlex.quote, so it is data, never code.
    """
    lines = ["set -- " + " ".join(shlex.quote(v) for v in request.positional)]
    lines += [f"export {name}={shlex.quote(value)}" for name, value in request.env.items()]
    lines.append(request.script)
    return ("\n".join(lines) + "\n").encode()


def remote_command(payload: bytes) -> str:
    return f"sh -c {shlex.quote(REMOTE_WRAPPER)} runpad {len(payload)}"


class SshExecutor:
    async def execute(self, request: ExecutionRequest, on_output: OutputCallback) -> int:
        endpoint = request.ssh
        if endpoint is None:
            raise ExecutionError("No SSH target")
        payload = build_payload(request)
        try:
            async with connect(endpoint) as conn:
                process = await conn.create_process(
                    remote_command(payload), encoding=None, stderr=asyncssh.STDOUT
                )
                process.stdin.write(payload)  # Not followed by EOF: stdin is the lifeline.
                try:
                    while chunk := await process.stdout.read(READ_SIZE):
                        await on_output(chunk)
                    result = await process.wait()
                finally:
                    await _close_lifeline(process)
        except _CONNECT_ERRORS as exc:
            raise ExecutionError(describe_error(exc, endpoint)) from exc
        if result.exit_status is not None:
            return result.exit_status
        return 128 + _signal_number(result.exit_signal)


async def _close_lifeline(process: asyncssh.SSHClientProcess[bytes]) -> None:
    """Signal the remote wrapper to stop the script, and give it time to do so."""
    if process.returncode is not None:
        return
    with contextlib.suppress(*_CONNECT_ERRORS):
        process.stdin.write_eof()
        async with asyncio.timeout(EXIT_GRACE_SECONDS):
            await process.wait()


def _signal_number(exit_signal: tuple[str, bool, str, str] | None) -> int:
    name = exit_signal[0] if exit_signal else "KILL"
    try:
        return int(signal.Signals[f"SIG{name}"])
    except KeyError:
        return int(signal.SIGKILL)
