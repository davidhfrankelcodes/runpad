"""HTTP requests to Targets."""

from dataclasses import dataclass

import httpx2 as httpx

from app.executors.ssh import ConnectionCheck

REQUEST_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class HttpEndpoint:
    base_url: str
    verify_tls: bool
    bearer_token: str | None


def client(endpoint: HttpEndpoint) -> httpx.AsyncClient:
    # Redirects are not followed so the bearer token is never sent to another host.
    headers = {"Authorization": f"Bearer {endpoint.bearer_token}"} if endpoint.bearer_token else {}
    return httpx.AsyncClient(
        base_url=endpoint.base_url,
        headers=headers,
        verify=endpoint.verify_tls,
        follow_redirects=False,
        timeout=REQUEST_TIMEOUT_SECONDS,
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
