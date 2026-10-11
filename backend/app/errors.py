"""Domain errors raised by business logic and mapped to HTTP responses in main.py."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class AuthenticationError(DomainError):
    status_code = 401


class PermissionDeniedError(DomainError):
    status_code = 403
