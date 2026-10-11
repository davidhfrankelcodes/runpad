import asyncio
from pathlib import Path

import pytest

from app.executors.base import ExecutionRequest
from app.executors.local import LocalExecutor


def _gone(pid: int) -> bool:
    """True if the process has exited (a zombie awaiting its parent counts as exited)."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return True
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


async def _run(request: ExecutionRequest) -> tuple[int, str]:
    output = bytearray()

    async def collect(chunk: bytes) -> None:
        output.extend(chunk)

    code = await LocalExecutor().execute(request, collect)
    return code, output.decode()


async def test_captures_stdout_and_stderr_with_exit_code() -> None:
    code, output = await _run(ExecutionRequest(script="echo out; echo err >&2; exit 3"))
    assert code == 3
    assert output == "out\nerr\n"


async def test_arguments_arrive_as_env_and_positional() -> None:
    request = ExecutionRequest(
        script='printf "%s|%s|%s" "$ARG_NAME" "$1" "$2"',
        positional=["web", "2"],
        env={"ARG_NAME": "web"},
    )
    assert await _run(request) == (0, "web|web|2")


async def test_argument_values_are_never_executed(tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    hostile = f"x; touch {marker}; $(touch {marker}) `touch {marker}`"
    request = ExecutionRequest(
        script='echo "$ARG_NAME"; echo "$1"', positional=[hostile], env={"ARG_NAME": hostile}
    )
    code, output = await _run(request)
    assert code == 0
    assert output == f"{hostile}\n{hostile}\n"
    assert not marker.exists()


async def test_app_environment_is_not_inherited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNPAD_SECRET_KEY", "must-not-leak")
    monkeypatch.setenv("DATABASE_URL", "postgresql://must-not-leak")
    code, output = await _run(ExecutionRequest(script="env"))
    assert code == 0
    assert "must-not-leak" not in output
    names = {line.split("=", 1)[0] for line in output.splitlines()}
    assert names <= {"PATH", "HOME", "LANG", "PWD", "SHLVL", "_"}


async def test_each_run_gets_a_private_workdir_that_is_removed() -> None:
    code, output = await _run(ExecutionRequest(script='pwd; [ "$HOME" = "$(pwd)" ] && ls -A'))
    workdir = output.splitlines()[0]
    assert code == 0
    assert output.splitlines()[1:] == []  # Empty directory.
    assert "runpad-run-" in workdir
    assert not Path(workdir).exists()


async def test_cancel_kills_the_whole_process_tree(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    request = ExecutionRequest(script=f"sleep 60 & echo $! > {pids}; echo $$ >> {pids}; wait")
    task = asyncio.create_task(_run(request))
    for _ in range(100):
        if pids.exists() and len(pids.read_text().split()) == 2:
            break
        await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(_gone(pid) for pid in map(int, pids.read_text().split()))


async def test_background_processes_do_not_outlive_the_run(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    code, _ = await _run(
        ExecutionRequest(script=f"sleep 60 >/dev/null 2>&1 & echo $! > {pid_file}")
    )
    assert code == 0
    assert _gone(int(pid_file.read_text()))
