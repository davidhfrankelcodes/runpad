"""SSH executor against an in-process fake server that runs commands with a local shell."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import asyncssh
import pytest

from app.executors.base import ExecutionError, ExecutionRequest, SshEndpoint
from app.executors.ssh import SshExecutor
from tests.fakes import FakeSshServer, fake_ssh_server
from tests.test_local_executor import _gone


@pytest.fixture
def server() -> Iterator[FakeSshServer]:
    with fake_ssh_server() as fake:
        yield fake


@pytest.fixture
def endpoint(server: FakeSshServer) -> SshEndpoint:
    key = asyncssh.generate_private_key("ssh-ed25519")
    server.authorize(key.export_public_key("openssh").decode())
    return SshEndpoint(
        host="127.0.0.1",
        port=server.port,
        username="runpad",
        host_key=server.host_key_line,
        private_key=key.export_private_key("openssh").decode(),
    )


async def _run(endpoint: SshEndpoint, script: str, **fields: object) -> tuple[int, str]:
    output = bytearray()

    async def collect(chunk: bytes) -> None:
        output.extend(chunk)

    request = ExecutionRequest(script=script, ssh=endpoint, **fields)  # type: ignore[arg-type]
    code = await SshExecutor().execute(request, collect)
    return code, output.decode()


async def _wait_for(path: Path) -> None:
    for _ in range(200):
        if path.exists() and path.read_text().strip():
            return
        await asyncio.sleep(0.025)
    raise AssertionError(f"{path} was not written")


async def test_merged_output_and_exit_code(endpoint: SshEndpoint) -> None:
    assert await _run(endpoint, "echo out; echo err >&2; exit 5") == (5, "out\nerr\n")


async def test_arguments_and_secrets_arrive_as_env_and_positional(endpoint: SshEndpoint) -> None:
    code, output = await _run(
        endpoint,
        'printf "%s|%s|%s|%s" "$ARG_NAME" "$1" "$2" "$TOKEN"',
        positional=["web", "two words"],
        env={"ARG_NAME": "web", "TOKEN": "t0k"},
    )
    assert (code, output) == (0, "web|web|two words|t0k")


async def test_nothing_from_the_action_appears_on_the_remote_command_line(
    endpoint: SshEndpoint, server: FakeSshServer
) -> None:
    await _run(
        endpoint,
        "echo the-script-text",
        positional=["arg-value"],
        env={"ARG_X": "arg-value", "TOKEN": "secret-value"},
    )
    [command] = server.commands
    for private in ("the-script-text", "arg-value", "secret-value", "TOKEN"):
        assert private not in command


async def test_hostile_values_are_data(endpoint: SshEndpoint, tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    hostile = f"'; touch {marker}; echo '$(touch {marker})`touch {marker}`\\"
    code, output = await _run(
        endpoint, 'echo "$ARG_X"; echo "$1"', positional=[hostile], env={"ARG_X": hostile}
    )
    assert (code, output) == (0, f"{hostile}\n{hostile}\n")
    assert not marker.exists()


async def test_script_cannot_read_the_lifeline(endpoint: SshEndpoint) -> None:
    # stdin is /dev/null for the script, so reading it ends immediately.
    assert await _run(endpoint, "cat; echo after") == (0, "after\n")


async def test_cancel_kills_the_remote_process_tree(endpoint: SshEndpoint, tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    script = f"sleep 60 & echo $! > {pids}; echo $$ >> {pids}; wait"
    task = asyncio.create_task(_run(endpoint, script))
    await _wait_for(pids)
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    for _ in range(100):
        if all(_gone(int(pid)) for pid in pids.read_text().split()):
            return
        await asyncio.sleep(0.05)
    raise AssertionError("remote processes survived cancellation")


async def test_background_processes_do_not_outlive_the_run(
    endpoint: SshEndpoint, tmp_path: Path
) -> None:
    pid_file = tmp_path / "pid"
    code, _ = await _run(endpoint, f"sleep 60 >/dev/null 2>&1 & echo $! > {pid_file}")
    assert code == 0
    for _ in range(100):
        if _gone(int(pid_file.read_text())):
            return
        await asyncio.sleep(0.05)
    raise AssertionError("background process outlived the run")


async def test_changed_host_key_fails(endpoint: SshEndpoint) -> None:
    other = asyncssh.generate_private_key("ssh-ed25519").export_public_key("openssh").decode()
    impostor = SshEndpoint(**{**endpoint.__dict__, "host_key": other})
    with pytest.raises(ExecutionError, match="does not match the pinned key"):
        await _run(impostor, "echo never")


async def test_unauthorized_key_fails(endpoint: SshEndpoint) -> None:
    stranger = asyncssh.generate_private_key("ssh-ed25519").export_private_key("openssh")
    denied = SshEndpoint(**{**endpoint.__dict__, "private_key": stranger.decode()})
    with pytest.raises(ExecutionError, match="Authentication failed"):
        await _run(denied, "echo never")
