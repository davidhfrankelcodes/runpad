import pytest

from app.executors.base import ExecutionError, ExecutionRequest, HttpCall, HttpEndpoint
from app.executors.http import HttpExecutor, placeholders, render_body, render_path
from tests.fakes import FakeHttpServer


def test_render_path_percent_encodes_each_value() -> None:
    path = render_path("api/states/{entity}?q={q}", {"entity": "light/../x y", "q": "a&b=c"})
    assert path == "api/states/light%2F..%2Fx%20y?q=a%26b%3Dc"


@pytest.mark.parametrize("value", [".", ".."])
def test_render_path_rejects_dot_segments(value: str) -> None:
    with pytest.raises(ExecutionError):
        render_path("api/{x}", {"x": value})


def test_render_body_keeps_types_and_never_parses_values_as_json() -> None:
    template = {"entity_id": "{entity}", "brightness": "{level}", "on": "{on}", "msg": "hi {who}"}
    values = {"entity": '"}, "evil": {"', "level": 7, "on": True, "who": "bob"}
    assert render_body(template, values) == {
        "entity_id": '"}, "evil": {"',
        "brightness": 7,
        "on": True,
        "msg": "hi bob",
    }


def test_placeholders_finds_nested_names() -> None:
    assert placeholders({"a": ["{x}", {"b": "pre {y} post"}], "{z}": 1}) == {"x", "y"}


async def _run(endpoint: HttpEndpoint, call: HttpCall) -> tuple[int, str]:
    output = bytearray()

    async def collect(chunk: bytes) -> None:
        output.extend(chunk)

    code = await HttpExecutor().execute(ExecutionRequest(http=endpoint, call=call), collect)
    return code, output.decode()


async def test_sends_request_with_bearer_token() -> None:
    with FakeHttpServer(required_token="tok") as server:
        endpoint = HttpEndpoint(base_url=server.url + "api/", verify_tls=True, bearer_token="tok")
        code, output = await _run(endpoint, HttpCall("POST", "lights/{x}", {"on": True}))
    assert code == 0
    assert output.startswith("HTTP 200 OK\n")
    [request] = server.requests
    assert request == {
        "method": "POST",
        "path": "/api/lights/%7Bx%7D",
        "body": {"on": True},
        "authorization": "Bearer tok",
    }


async def test_non_success_status_is_the_exit_code() -> None:
    with FakeHttpServer(status=503) as server:
        endpoint = HttpEndpoint(base_url=server.url, verify_tls=True, bearer_token=None)
        code, output = await _run(endpoint, HttpCall("GET", ""))
    assert code == 503
    assert output.startswith("HTTP 503 ")


async def test_unreachable_target_is_an_execution_error() -> None:
    endpoint = HttpEndpoint(base_url="http://127.0.0.1:1/", verify_tls=True, bearer_token=None)
    with pytest.raises(ExecutionError, match="Request failed"):
        await _run(endpoint, HttpCall("GET", ""))
