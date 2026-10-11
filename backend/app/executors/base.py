from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

OutputCallback = Callable[[bytes], Awaitable[None]]


class ExecutionError(Exception):
    """The command could not be run (as opposed to running and exiting non-zero)."""


@dataclass(frozen=True)
class ExecutionRequest:
    script: str
    # Argument values, in definition order, passed as $1, $2, ...
    positional: list[str] = field(default_factory=list)
    # ARG_<NAME> variables and secret variables. Never the app's own environment.
    env: dict[str, str] = field(default_factory=dict)


class Executor(Protocol):
    async def execute(self, request: ExecutionRequest, on_output: OutputCallback) -> int:
        """Run the request, stream merged stdout/stderr to on_output, return the exit code.

        Must clean up (kill processes, close connections) when cancelled.
        """
        ...
