"""Run commands inside the app container. Cannot touch the host."""

import asyncio
import contextlib
import os
import shutil
import signal
import tempfile
from asyncio.subprocess import DEVNULL, PIPE, STDOUT, Process

from app.executors.base import ExecutionError, ExecutionRequest, OutputCallback

# The command never inherits the app's environment (DATABASE_URL, RUNPAD_SECRET_KEY).
BASE_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8",
}
TERMINATE_GRACE_SECONDS = 3
READ_SIZE = 4096


class LocalExecutor:
    async def execute(self, request: ExecutionRequest, on_output: OutputCallback) -> int:
        # Each Run gets a private, empty working directory (also its HOME), removed afterwards.
        workdir = await asyncio.to_thread(tempfile.mkdtemp, prefix="runpad-run-")
        try:
            return await self._execute(request, on_output, workdir)
        finally:
            await asyncio.to_thread(shutil.rmtree, workdir, ignore_errors=True)

    async def _execute(
        self, request: ExecutionRequest, on_output: OutputCallback, workdir: str
    ) -> int:
        try:
            process = await asyncio.create_subprocess_exec(
                "/bin/sh",
                "-c",
                request.script,
                "runpad",  # $0; arguments start at $1.
                *request.positional,
                stdin=DEVNULL,
                stdout=PIPE,
                stderr=STDOUT,
                env={**BASE_ENV, "HOME": workdir, **request.env},
                cwd=workdir,
                start_new_session=True,  # Own process group, so the whole tree can be killed.
            )
        except OSError as exc:
            raise ExecutionError(f"Could not start /bin/sh: {exc}") from exc

        stdout = process.stdout
        if stdout is None:  # Only possible if stdout=PIPE above is removed.
            raise ExecutionError("No output pipe")
        try:
            while chunk := await stdout.read(READ_SIZE):
                await on_output(chunk)
            return await process.wait()
        finally:
            await _kill_group(process)


async def _kill_group(process: Process) -> None:
    """Stop the command and anything it started. Runs never leave processes behind."""
    if process.returncode is None:
        _signal_group(process, signal.SIGTERM)
        try:
            async with asyncio.timeout(TERMINATE_GRACE_SECONDS):
                await process.wait()
        except TimeoutError:
            pass
    _signal_group(process, signal.SIGKILL)
    if process.returncode is None:
        await process.wait()


def _signal_group(process: Process, sig: signal.Signals) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, sig)
