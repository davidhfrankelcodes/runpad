"""Run lifecycle: start, execute with a timeout, capture and redact output, persist.

Runs execute in-process as asyncio tasks. There is no job queue. Live output is held in
memory while a Run is active and streamed to subscribers; the final output is stored on
the Run row.
"""

import asyncio
import codecs
import logging
import re
import uuid
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import runs, secret_store, targets
from app.errors import ConflictError, DomainError
from app.events import Event, EventBus
from app.executors import get_executor
from app.executors.base import ExecutionError, ExecutionRequest, HttpCall
from app.executors.base import Executor as ExecutorImpl
from app.executors.http import render_body, render_path
from app.models import (
    Action,
    Concurrency,
    Executor,
    Run,
    RunStatus,
    Secret,
    SecretKind,
    Target,
    User,
)
from app.schemas.actions import ArgSpec, ArgValue, HttpSpec, ScriptSpec, SecretEnv
from app.security import SecretCipher, utcnow

logger = logging.getLogger(__name__)

OUTPUT_LIMIT_BYTES = 512 * 1024
REDACTED = "[redacted]"
KEEPALIVE_SECONDS = 15

_arg_specs = TypeAdapter(list[ArgSpec])
_secret_env = TypeAdapter(list[SecretEnv])


# --- Arguments -------------------------------------------------------------


def validate_args(specs: list[ArgSpec], values: dict[str, ArgValue]) -> dict[str, ArgValue]:
    """Check supplied values against the Action's typed arguments and fill in defaults."""
    unknown = set(values) - {spec.name for spec in specs}
    if unknown:
        raise DomainError(f"Unknown arguments: {', '.join(sorted(unknown))}")
    result: dict[str, ArgValue] = {}
    errors: list[str] = []
    for spec in specs:
        value = values.get(spec.name, spec.default)
        if value is None:
            errors.append(f"{spec.name}: required")
            continue
        try:
            result[spec.name] = spec.check_value(value)
        except ValueError as exc:
            errors.append(f"{spec.name}: {exc}")
    if errors:
        raise DomainError("; ".join(errors))
    return result


def arg_to_str(value: ArgValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_script_request(
    spec: ScriptSpec, specs: list[ArgSpec], values: dict[str, ArgValue], secrets: dict[str, str]
) -> ExecutionRequest:
    """Arguments become $ARG_<NAME> and $1..$n. They are never put into the script text."""
    env = {f"ARG_{s.name.upper()}": arg_to_str(values[s.name]) for s in specs}
    return ExecutionRequest(
        script=spec.script,
        positional=[arg_to_str(values[s.name]) for s in specs],
        env={**spec.env, **secrets, **env},
    )


def build_http_call(spec: HttpSpec, values: dict[str, ArgValue]) -> HttpCall:
    try:
        path = render_path(spec.path, values)
    except ExecutionError as exc:
        raise DomainError(str(exc)) from exc
    return HttpCall(method=spec.method, path=path, body=render_body(spec.body, values))


async def _reveal_secret_env(
    db: AsyncSession, cipher: SecretCipher, items: list[SecretEnv]
) -> dict[str, str]:
    env: dict[str, str] = {}
    for item in items:
        secret = await db.get(Secret, item.secret_id)
        if secret is None or secret.kind != SecretKind.TEXT:
            raise DomainError(f"Secret for ${item.name} is missing")
        env[item.name] = secret_store.reveal(cipher, secret)
    return env


async def prepare_request(
    db: AsyncSession,
    cipher: SecretCipher,
    *,
    name: str,
    executor: Executor,
    target_id: uuid.UUID | None,
    spec: ScriptSpec | HttpSpec,
    specs: list[ArgSpec],
    args: dict[str, ArgValue],
    secret_env: list[SecretEnv],
) -> tuple[ExecutionRequest, list[str]]:
    """Build an executor request, and list every secret value to redact from its output.

    Used for Runs and for State polling, so both resolve targets and secrets the same way.
    """
    env = await _reveal_secret_env(db, cipher, secret_env)
    mismatch = DomainError(f"{name}: the command does not match the {executor.value} executor")
    target = await db.get(Target, target_id) if target_id else None
    if executor == Executor.HTTP:
        if not isinstance(spec, HttpSpec):
            raise mismatch
        if target is None:
            raise DomainError(f"{name} has no target")
        http_endpoint = await targets.http_endpoint(db, cipher, target)
        token = [http_endpoint.bearer_token] if http_endpoint.bearer_token else []
        return ExecutionRequest(http=http_endpoint, call=build_http_call(spec, args)), token

    if not isinstance(spec, ScriptSpec):
        raise mismatch
    request = build_script_request(spec, specs, args, env)
    if executor == Executor.LOCAL:
        return request, list(env.values())
    if target is None:
        raise DomainError(f"{name} has no target")
    endpoint = await targets.ssh_endpoint(db, cipher, target)
    return replace(request, ssh=endpoint), [*env.values(), endpoint.private_key]


# --- Redaction -------------------------------------------------------------


class Redactor:
    """Replaces secret values in streamed text, including values split across chunks."""

    def __init__(self, secrets: Iterable[str]) -> None:
        values = sorted(
            {v for secret in secrets for v in (secret, secret.strip()) if v},
            key=len,
            reverse=True,
        )
        self._pattern = re.compile("|".join(map(re.escape, values))) if values else None
        # Text that might be the start of a secret is held back until more arrives.
        self._holdback = max((len(v) for v in values), default=1) - 1
        self._pending = ""

    def redact(self, value: str) -> str:
        return self._pattern.sub(REDACTED, value) if self._pattern else value

    def feed(self, chunk: str) -> str:
        if self._pattern is None:
            return chunk
        buffer = self._pending + chunk
        cut = max(len(buffer) - self._holdback, 0)
        # Never cut through a match that starts before the cut point.
        for match in self._pattern.finditer(buffer):
            if match.start() >= cut:
                break
            cut = max(cut, match.end())
        self._pending = buffer[cut:]
        return self.redact(buffer[:cut])

    def flush(self) -> str:
        rest, self._pending = self._pending, ""
        return self.redact(rest)


# --- Active runs -----------------------------------------------------------


@dataclass
class ActiveRun:
    """A Run in progress: its output so far, and a way to follow new output."""

    run_id: uuid.UUID
    redactor: Redactor
    feature_instance_id: uuid.UUID | None = None
    chunks: list[str] = field(default_factory=list)
    size: int = 0
    truncated: bool = False
    finished: bool = False
    cancel_status: RunStatus = RunStatus.CANCELLED
    task: asyncio.Task[None] | None = None
    _decoder: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")(errors="replace")
    )
    _changed: asyncio.Condition = field(default_factory=asyncio.Condition)

    @property
    def output(self) -> str:
        return "".join(self.chunks)

    async def on_output(self, data: bytes) -> None:
        await self._append(self.redactor.feed(self._decoder.decode(data)))

    async def flush(self) -> None:
        """Emit any output held back by the decoder and redactor."""
        await self._append(self.redactor.feed(self._decoder.decode(b"", final=True)))
        await self._append(self.redactor.flush())

    async def finish(self) -> None:
        """Tell followers the Run is over. Call after its final state is stored."""
        async with self._changed:
            self.finished = True
            self._changed.notify_all()

    async def _append(self, chunk: str) -> None:
        if not chunk or self.truncated:
            return  # Past the limit, output is drained and discarded.
        encoded = chunk.encode()
        if self.size + len(encoded) > OUTPUT_LIMIT_BYTES:
            chunk = encoded[: OUTPUT_LIMIT_BYTES - self.size].decode(errors="ignore")
            self.truncated = True
        self.size += len(chunk.encode())
        async with self._changed:
            self.chunks.append(chunk)
            self._changed.notify_all()

    async def follow(self) -> AsyncIterator[str | None]:
        """Yield all output so far, then new output as it arrives, until the Run ends.

        Yields None periodically while idle, so callers can send keepalives.
        """
        index = 0
        while True:
            async with self._changed:
                try:
                    async with asyncio.timeout(KEEPALIVE_SECONDS):
                        await self._changed.wait_for(
                            lambda seen=index: seen < len(self.chunks) or self.finished
                        )
                except TimeoutError:
                    yield None
                    continue
                new, index, finished = self.chunks[index:], len(self.chunks), self.finished
            for chunk in new:
                yield chunk
            if finished:
                return


# --- Runner ----------------------------------------------------------------


class Runner:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        cipher: SecretCipher,
        bus: EventBus,
        on_feature_run: Callable[[uuid.UUID], None] | None = None,
    ) -> None:
        """`on_feature_run` is called with the Feature instance after each Run of one of
        its Actions finishes."""
        self._sessionmaker = sessionmaker
        self._cipher = cipher
        self._bus = bus
        self._on_feature_run = on_feature_run
        self._active: dict[uuid.UUID, ActiveRun] = {}

    def _publish(self, run: Run, username: str | None) -> None:
        self._bus.publish(
            Event(
                name="run",
                data=runs.to_read(run, username).model_dump(mode="json"),
                user_id=run.user_id,
            )
        )

    def active(self, run_id: uuid.UUID) -> ActiveRun | None:
        return self._active.get(run_id)

    async def load(self, run_id: uuid.UUID) -> tuple[Run, str | None]:
        """A Run and its user's name, read in a fresh session (for use after streaming)."""
        async with self._sessionmaker() as db:
            row = (
                await db.execute(
                    select(Run, User.username)
                    .outerjoin(User, Run.user_id == User.id)
                    .where(Run.id == run_id)
                )
            ).one()
            return row[0], row[1]

    async def recover(self) -> int:
        """On startup, mark Runs left `running` by a previous process as interrupted."""
        async with self._sessionmaker() as db:
            result = await db.execute(
                update(Run)
                .where(Run.status == RunStatus.RUNNING)
                .values(
                    status=RunStatus.INTERRUPTED,
                    finished_at=utcnow(),
                    error="runpad stopped while this run was in progress",
                )
            )
            await db.commit()
        return result.rowcount  # type: ignore[attr-defined, no-any-return]

    async def shutdown(self) -> None:
        """Stop active Runs and record them as interrupted."""
        tasks = []
        for active in list(self._active.values()):
            active.cancel_status = RunStatus.INTERRUPTED
            if active.task is not None:
                active.task.cancel()
                tasks.append(active.task)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def cancel(self, run_id: uuid.UUID) -> bool:
        active = self._active.get(run_id)
        if active is None or active.task is None or active.finished:
            return False
        active.task.cancel()
        await asyncio.gather(active.task, return_exceptions=True)
        return True

    async def start(
        self,
        db: AsyncSession,
        action: Action,
        values: dict[str, ArgValue],
        user: User | None,
    ) -> Run:
        """Validate, record, and launch a Run. Returns immediately; the Run continues in
        the background."""
        specs = _arg_specs.validate_python(action.args)
        args = validate_args(specs, values)
        executor = get_executor(action.executor)
        request, secrets = await self._prepare(db, action, specs, args)

        if action.concurrency == Concurrency.REJECT:
            # Serialize starts for this Action until commit, then check for a running Run.
            await db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": int.from_bytes(action.id.bytes[:8], "big", signed=True)},
            )
            running = await db.scalar(
                select(Run.id).where(Run.action_id == action.id, Run.status == RunStatus.RUNNING)
            )
            if running is not None:
                raise ConflictError(f"{action.name} is already running")

        run = Run(
            id=uuid.uuid4(),
            action_id=action.id,
            action_name=action.name,
            user_id=user.id if user else None,
            args=args,
            status=RunStatus.RUNNING,
            started_at=utcnow(),
        )
        db.add(run)
        await db.commit()
        self._publish(run, user.username if user else None)

        active = ActiveRun(
            run_id=run.id,
            redactor=Redactor(secrets),
            feature_instance_id=action.feature_instance_id,
        )
        self._active[run.id] = active
        active.task = asyncio.create_task(
            self._execute(active, executor, request, action.timeout_seconds),
            name=f"run-{run.id}",
        )
        return run

    async def _prepare(
        self,
        db: AsyncSession,
        action: Action,
        specs: list[ArgSpec],
        args: dict[str, ArgValue],
    ) -> tuple[ExecutionRequest, list[str]]:
        spec_model = HttpSpec if action.executor == Executor.HTTP else ScriptSpec
        return await prepare_request(
            db,
            self._cipher,
            name=action.name,
            executor=action.executor,
            target_id=action.target_id,
            spec=spec_model.model_validate(action.spec),
            specs=specs,
            args=args,
            secret_env=_secret_env.validate_python(action.secret_env),
        )

    async def _execute(
        self,
        active: ActiveRun,
        executor: ExecutorImpl,
        request: ExecutionRequest,
        timeout_seconds: int,
    ) -> None:
        status = RunStatus.FAILED
        exit_code: int | None = None
        error: str | None = None
        deadline = asyncio.timeout(timeout_seconds)
        try:
            async with deadline:
                exit_code = await executor.execute(request, active.on_output)
            status = RunStatus.SUCCEEDED if exit_code == 0 else RunStatus.FAILED
        except TimeoutError as exc:
            if deadline.expired():
                status, error = RunStatus.TIMED_OUT, f"Timed out after {timeout_seconds} seconds"
            else:  # A timeout inside the executor, such as a connection timeout.
                error = active.redactor.redact(str(exc) or "Operation timed out")
        except asyncio.CancelledError:
            status = active.cancel_status
            error = (
                "Cancelled"
                if status == RunStatus.CANCELLED
                else "runpad stopped while this run was in progress"
            )
        except ExecutionError as exc:
            error = active.redactor.redact(str(exc))
        except Exception:
            logger.exception("Run %s failed unexpectedly", active.run_id)
            error = "Internal error; see the runpad logs"
        finally:
            await active.flush()
            await self._persist(active, status, exit_code, error)
            self._active.pop(active.run_id, None)
            await active.finish()
            if active.feature_instance_id is not None and self._on_feature_run is not None:
                # A feature's button probably changed its State; check now.
                self._on_feature_run(active.feature_instance_id)

    async def _persist(
        self, active: ActiveRun, status: RunStatus, exit_code: int | None, error: str | None
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "finished_at": utcnow(),
            "exit_code": exit_code,
            "output": active.output,
            "output_truncated": active.truncated,
            "error": error,
        }
        try:
            async with self._sessionmaker() as db:
                await db.execute(update(Run).where(Run.id == active.run_id).values(**values))
                await db.commit()
        except Exception:
            logger.exception("Could not record the result of run %s", active.run_id)
            return
        try:
            self._publish(*await self.load(active.run_id))
        except Exception:
            logger.exception("Could not announce the result of run %s", active.run_id)
