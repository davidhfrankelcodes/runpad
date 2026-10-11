"""In-process fakes for executor tests. Never touch real hosts."""

import asyncio
import json
import threading
from asyncio.subprocess import PIPE
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import asyncssh


def _key_line(key: asyncssh.SSHKey) -> str:
    return " ".join(key.export_public_key("openssh").decode().split()[:2])


class FakeSshServer:
    """An asyncssh server on 127.0.0.1 with a mutable set of authorized client keys."""

    def __init__(self) -> None:
        self.host_key = asyncssh.generate_private_key("ssh-ed25519")
        self.host_key_line = _key_line(self.host_key)
        self.host_keys: list[asyncssh.SSHKey] = []  # Offered in addition to host_key.
        self.commands: list[str] = []  # Every command line received, for inspection.
        self.authorized: set[str] = set()
        self.port = 0
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)

    def authorize(self, public_key_line: str) -> None:
        self.authorized.add(" ".join(public_key_line.split()[:2]))

    def start(self) -> None:
        self._thread.start()
        fake = self

        class Server(asyncssh.SSHServer):
            def begin_auth(self, username: str) -> bool:
                return True

            def public_key_auth_supported(self) -> bool:
                return True

            def validate_public_key(self, username: str, key: asyncssh.SSHKey) -> bool:
                return _key_line(key) in fake.authorized

        async def run_command(process: asyncssh.SSHServerProcess[bytes]) -> None:
            """Run the command with a local shell, like sshd would on a real host."""
            command = process.command or ""
            fake.commands.append(command)
            local = await asyncio.create_subprocess_shell(
                command, stdin=PIPE, stdout=PIPE, stderr=PIPE
            )
            await process.redirect(stdin=local.stdin, stdout=local.stdout, stderr=local.stderr)
            process.exit(await local.wait())
            await process.wait_closed()  # Lets asyncssh finish its redirect cleanup.

        async def serve() -> asyncssh.SSHAcceptor:
            return await asyncssh.create_server(
                Server,
                "127.0.0.1",
                0,
                server_host_keys=[*self.host_keys, self.host_key],
                process_factory=run_command,
                encoding=None,
            )

        self._server = asyncio.run_coroutine_threadsafe(serve(), self._loop).result(10)
        self.port = self._server.sockets[0].getsockname()[1]

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._server.close)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)


@contextmanager
def fake_ssh_server() -> Iterator[FakeSshServer]:
    server = FakeSshServer()
    server.start()
    try:
        yield server
    finally:
        server.stop()


class FakeHttpServer:
    """Records every request. Answers with `status` and a JSON echo of the request, or 401
    if a required bearer token is missing or wrong."""

    def __init__(self, required_token: str | None = None, status: int = 200) -> None:
        self.required_token = required_token
        self.status = status
        self.seen_authorization: list[str | None] = []
        self.requests: list[dict[str, object]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self) -> None:
                auth = self.headers.get("Authorization")
                fake.seen_authorization.append(auth)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                request = {
                    "method": self.command,
                    "path": self.path,
                    "body": json.loads(raw) if raw else None,
                    "authorization": auth,
                }
                fake.requests.append(request)
                ok = fake.required_token is None or auth == f"Bearer {fake.required_token}"
                payload = json.dumps(request).encode()
                self.send_response(fake.status if ok else 401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeHttpServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()


@contextmanager
def fake_ssh_server_with_keys(*algorithms: str) -> Iterator[FakeSshServer]:
    """A fake server offering several host keys, in the given order."""
    server = FakeSshServer()
    server.host_keys = [asyncssh.generate_private_key(alg) for alg in algorithms]
    server.start()
    try:
        yield server
    finally:
        server.stop()
