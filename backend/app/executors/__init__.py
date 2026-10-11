from app.errors import DomainError
from app.executors.base import Executor
from app.executors.local import LocalExecutor
from app.models import Executor as ExecutorKind

_EXECUTORS: dict[ExecutorKind, Executor] = {
    ExecutorKind.LOCAL: LocalExecutor(),
}


def get_executor(kind: ExecutorKind) -> Executor:
    try:
        return _EXECUTORS[kind]
    except KeyError:
        raise DomainError(f"The {kind.value} executor is not available") from None
