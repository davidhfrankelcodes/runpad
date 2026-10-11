"""Checks that run from the runpad container: website, TCP port, and TLS certificate."""

import os
import socket
import subprocess
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.features import port_check, tls_certificate, website_check
from app.features.base import ProbeResult
from app.models import Executor, StateTone
from app.schemas.actions import ScriptSpec
from tests.fakes import FakeHttpServer


def _state(
    parse: Callable,
    config: object,
    exit_code: int | None,
    output: str = "",
    error: str | None = None,
) -> tuple[str, StateTone, str]:
    [state] = parse(config, ProbeResult(exit_code, output, error))
    return state.value, state.tone, state.detail


def _probe(probe: Callable, config: object) -> ProbeResult:
    """Run a feature's probe script with sh, as the local executor would."""
    spec = probe(config).spec
    assert isinstance(spec, ScriptSpec)
    result = subprocess.run(  # noqa: S603 - the feature's own fixed script
        ["/bin/sh", "-c", spec.script],
        env={**os.environ, **spec.env},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return ProbeResult(result.returncode, result.stdout + result.stderr)


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# --- Website check ---------------------------------------------------------

SITE = website_check.ConfigModel(url="https://example.com/health", name="Blog")


def test_website_build_and_probe() -> None:
    built = website_check.build(SITE)
    assert built.actions == []
    assert [(t.state_key, t.label) for t in built.tiles] == [("site", "Blog")]
    probe = website_check.probe(SITE)
    assert probe.executor == Executor.LOCAL
    assert isinstance(probe.spec, ScriptSpec)
    assert probe.spec.env == {"URL": "https://example.com/health"}
    assert "example.com" not in probe.spec.script


@pytest.mark.parametrize(
    "url", ["example.com", "ftp://x", "http://", "https://a b", "javascript:1"]
)
def test_website_rejects_bad_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        website_check.ConfigModel(url=url, name="x")


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, ("up", StateTone.GOOD)),
        (204, ("up", StateTone.GOOD)),
        (404, ("error", StateTone.BAD)),
        (503, ("error", StateTone.BAD)),
    ],
)
def test_website_probe_against_a_server(status: int, expected: tuple) -> None:
    with FakeHttpServer(status=status) as server:
        config = website_check.ConfigModel(url=server.url + "health", name="x")
        result = _probe(website_check.probe, config)
    value, tone, detail = _state(website_check.parse, config, result.exit_code, result.output)
    assert (value, tone) == expected
    assert detail.startswith(f"HTTP {status} · ")
    assert detail.endswith(" ms")
    assert server.requests[0]["path"] == "/health"


def test_website_probe_when_nothing_listens() -> None:
    config = website_check.ConfigModel(url=f"http://127.0.0.1:{_closed_port()}/", name="x")
    result = _probe(website_check.probe, config)
    value, tone, detail = _state(website_check.parse, config, result.exit_code, result.output)
    assert (value, tone) == ("down", StateTone.BAD)
    assert "refused" in detail.lower()


def test_website_parse_failures() -> None:
    assert _state(website_check.parse, SITE, None, error="Timed out") == (
        "unknown",
        StateTone.UNKNOWN,
        "Timed out",
    )
    assert _state(website_check.parse, SITE, 127, "sh: python3: not found\n") == (
        "unknown",
        StateTone.UNKNOWN,
        "sh: python3: not found",
    )


# --- Port check ------------------------------------------------------------


def test_port_build() -> None:
    config = port_check.ConfigModel(host="db.lan", port=5432)
    built = port_check.build(config)
    assert built.actions == []
    assert [(t.state_key, t.label) for t in built.tiles] == [("port", "db.lan:5432")]
    spec = port_check.probe(config).spec
    assert isinstance(spec, ScriptSpec)
    assert spec.env == {"HOST": "db.lan", "PORT": "5432"}


@pytest.mark.parametrize("field", [{"host": "a b"}, {"host": "-x"}, {"port": 0}, {"port": 70000}])
def test_port_rejects_bad_config(field: dict) -> None:
    with pytest.raises(ValidationError):
        port_check.ConfigModel(**{"host": "db", "port": 22, **field})


def test_port_probe_open_and_closed() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        config = port_check.ConfigModel(host="127.0.0.1", port=listener.getsockname()[1])
        result = _probe(port_check.probe, config)
    value, tone, detail = _state(port_check.parse, config, result.exit_code, result.output)
    assert (value, tone) == ("open", StateTone.GOOD)
    assert detail.endswith(" ms")

    config = port_check.ConfigModel(host="127.0.0.1", port=_closed_port())
    result = _probe(port_check.probe, config)
    value, tone, detail = _state(port_check.parse, config, result.exit_code, result.output)
    assert (value, tone) == ("closed", StateTone.BAD)
    assert "refused" in detail.lower()


# --- TLS certificate -------------------------------------------------------

CERT = tls_certificate.ConfigModel(host="example.com")
NOW = 1_800_000_000  # 2027-01-15.
DAY = 86400


def test_tls_build() -> None:
    built = tls_certificate.build(CERT)
    assert [(t.state_key, t.label) for t in built.tiles] == [("certificate", "example.com")]
    other = tls_certificate.build(tls_certificate.ConfigModel(host="mail.lan", port=993))
    assert other.tiles[0].label == "mail.lan:993"
    spec = tls_certificate.probe(CERT).spec
    assert isinstance(spec, ScriptSpec)
    assert spec.env == {"HOST": "example.com", "PORT": "443"}


@pytest.mark.parametrize(
    ("output", "exit_code", "expected"),
    [
        (
            f"expires {NOW + 90 * DAY}\n",
            0,
            ("90 days left", StateTone.GOOD, "Valid until 2027-04-15"),
        ),
        (
            f"expires {NOW + 14 * DAY}\n",
            0,
            ("14 days left", StateTone.GOOD, "Valid until 2027-01-29"),
        ),
        (
            f"expires {NOW + 13 * DAY}\n",
            0,
            ("13 days left", StateTone.WARN, "Valid until 2027-01-28"),
        ),
        (f"expires {NOW + DAY + 5}\n", 0, ("1 day left", StateTone.WARN, "Valid until 2027-01-16")),
        (f"expires {NOW + 3600}\n", 0, ("expires today", StateTone.WARN, "Valid until 2027-01-15")),
        (
            "invalid certificate has expired\n",
            3,
            ("invalid", StateTone.BAD, "certificate has expired"),
        ),
        (
            "invalid Hostname mismatch, certificate is not valid for 'example.com'.\n",
            3,
            (
                "invalid",
                StateTone.BAD,
                "Hostname mismatch, certificate is not valid for 'example.com'.",
            ),
        ),
        ("error Connection refused\n", 2, ("unreachable", StateTone.BAD, "Connection refused")),
    ],
)
def test_tls_parse(output: str, exit_code: int, expected: tuple) -> None:
    [state] = tls_certificate.parse(CERT, ProbeResult(exit_code, output), now=NOW)
    assert (state.value, state.tone, state.detail) == expected


def test_tls_probe_against_a_server_without_tls() -> None:
    with FakeHttpServer() as server:
        port = int(server.url.rsplit(":", 1)[1].strip("/"))
        config = tls_certificate.ConfigModel(host="127.0.0.1", port=port)
        result = _probe(tls_certificate.probe, config)
    value, tone, _ = _state(tls_certificate.parse, config, result.exit_code, result.output)
    assert (value, tone) == ("unreachable", StateTone.BAD)
