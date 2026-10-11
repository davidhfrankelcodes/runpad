"""HTTP requests to Targets."""

import re
from typing import Any
from urllib.parse import quote

import httpx2 as httpx

from app.executors.base import (
    ConnectionCheck,
    ExecutionError,
    ExecutionRequest,
    HttpCall,
    HttpEndpoint,
    OutputCallback,
)

REQUEST_TIMEOUT_SECONDS = 10
PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]{0,31})\}")


def client(endpoint: HttpEndpoint, timeout: float = REQUEST_TIMEOUT_SECONDS) -> httpx.AsyncClient:
    # Redirects are not followed so the bearer token is never sent to another host.
    headers = {"Authorization": f"Bearer {endpoint.bearer_token}"} if endpoint.bearer_token else {}
    return httpx.AsyncClient(
        base_url=endpoint.base_url,
        headers=headers,
        verify=endpoint.verify_tls,
        follow_redirects=False,
        timeout=timeout,
    )


async def check_connection(endpoint: HttpEndpoint) -> ConnectionCheck:
    """GET the base URL. Any response counts as reachable unless auth is rejected."""
    try:
        async with client(endpoint) as http:
            response = await http.get("")
    except httpx.HTTPError as exc:
        return ConnectionCheck(ok=False, message=f"Could not connect: {exc}")
    if response.status_code in (401, 403):
        return ConnectionCheck(
            ok=False,
            message=f"Reachable, but authentication was rejected (HTTP {response.status_code})",
        )
    return ConnectionCheck(ok=True, message=f"Reachable (HTTP {response.status_code})")


def placeholders(template: Any) -> set[str]:
    """Names referenced as {name} anywhere in a path or JSON body template."""
    if isinstance(template, str):
        return set(PLACEHOLDER.findall(template))
    if isinstance(template, dict):
        return set().union(*(placeholders(v) for v in template.values()))
    if isinstance(template, list):
        return set().union(*(placeholders(v) for v in template))
    return set()


def _text(value: str | int | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_path(template: str, values: dict[str, str | int | bool]) -> str:
    """Fill {name} placeholders, percent-encoding each value as one path segment."""

    def fill(match: re.Match[str]) -> str:
        value = _text(values[match.group(1)])
        if value in {".", ".."}:
            raise ExecutionError(f"{match.group(1)}: {value!r} is not allowed in a URL path")
        return quote(value, safe="")

    return PLACEHOLDER.sub(fill, template)


def render_body(template: Any, values: dict[str, str | int | bool]) -> Any:
    """Fill placeholders in parsed JSON. A string that is exactly "{name}" becomes the typed
    value; placeholders inside longer strings are replaced with the value's text."""
    if isinstance(template, str):
        whole = PLACEHOLDER.fullmatch(template)
        if whole:
            return values[whole.group(1)]
        return PLACEHOLDER.sub(lambda m: _text(values[m.group(1)]), template)
    if isinstance(template, dict):
        return {key: render_body(value, values) for key, value in template.items()}
    if isinstance(template, list):
        return [render_body(item, values) for item in template]
    return template


class HttpExecutor:
    async def execute(self, request: ExecutionRequest, on_output: OutputCallback) -> int:
        endpoint, call = request.http, request.call
        if endpoint is None or call is None:
            raise ExecutionError("No HTTP target")
        # The Run's own timeout bounds the whole request; this only bounds each read/connect.
        try:
            async with (
                client(endpoint) as http,
                http.stream(
                    call.method, call.path, json=call.body if call.body is not None else None
                ) as response,
            ):
                await on_output(f"HTTP {response.status_code} {response.reason_phrase}\n".encode())
                async for chunk in response.aiter_bytes():
                    await on_output(chunk)
        except httpx.HTTPError as exc:
            raise ExecutionError(f"Request failed: {exc}") from exc
        return 0 if response.is_success else response.status_code


__all__ = ["HttpCall", "HttpEndpoint", "HttpExecutor", "check_connection", "client"]
