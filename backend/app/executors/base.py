from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

OutputCallback = Callable[[bytes], Awaitable[None]]


class ExecutionError(Exception):
    """The command could not be run (as opposed to running and exiting non-zero)."""


@dataclass(frozen=True)
class ConnectionCheck:
    ok: bool
    message: str


@dataclass(frozen=True)
class SshEndpoint:
    host: str
    port: int
    username: str
    host_key: str
    private_key: str


@dataclass(frozen=True)
class HttpEndpoint:
    base_url: str
    verify_tls: bool
    bearer_token: str | None


@dataclass(frozen=True)
class HttpCall:
    """A fully resolved request: placeholders already filled in and encoded."""

    method: str
    path: str
    body: Any = None  # JSON-serializable, or None for no body.


@dataclass(frozen=True)
class ExecutionRequest:
    # local and ssh: the script, run with sh.
    script: str = ""
    # Argument values, in definition order, passed as $1, $2, ...
    positional: list[str] = field(default_factory=list)
    # ARG_<NAME> variables and secret variables. Never the app's own environment.
    env: dict[str, str] = field(default_factory=dict)
    ssh: SshEndpoint | None = None
    http: HttpEndpoint | None = None
    call: HttpCall | None = None


class Executor(Protocol):
    async def execute(self, request: ExecutionRequest, on_output: OutputCallback) -> int:
        """Run the request, stream merged stdout/stderr to on_output, return the exit code.

        Must clean up (kill processes, close connections) when cancelled.
        """
        ...
