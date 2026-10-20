"""The restic backup feature: its parser against real restic output, and its scripts against a
stand-in restic and sudo."""

import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.features import restic_backup
from app.features.base import ProbeResult
from app.models import StateTone
from app.schemas.actions import ScriptSpec

TARGET = uuid.uuid4()

# `restic snapshots --json --latest 1` from restic 0.19.1: the latest snapshot of each host
# and path set, times in nanoseconds.
SNAPSHOTS = (
    '[{"time":"2026-10-19T23:21:38.805701244Z","tree":"9c50efdf","paths":["/etc/hostname",'
    '"/etc/os-release"],"hostname":"nas","username":"root","program_version":"restic 0.19.1",'
    '"id":"4fc38a0c37aeef50","short_id":"4fc38a0c"},{"time":"2026-10-19T23:21:39.798534674Z",'
    '"parent":"4fc38a0c37aeef50","tree":"397bb25b","paths":["/etc/hostname"],"hostname":"nas",'
    '"username":"root","program_version":"restic 0.19.1","id":"4a27250ed0977552",'
    '"short_id":"4a27250e"}]'
)
LATEST = int(datetime.fromisoformat("2026-10-19T23:21:40Z").timestamp())  # Rounded up.
WRONG_PASSWORD = (
    '{"message_type":"exit_error","code":12,"message":"Fatal: wrong password or no key found"}'
)
NO_REPOSITORY = (
    '{"message_type":"exit_error","code":10,"message":"Fatal: repository does not exist: '
    "unable to open config file: stat /nope/config: no such file or directory\\nIs there a "
    'repository at the following location?\\n/nope"}'
)


def _config(**extra: object) -> restic_backup.ConfigModel:
    return restic_backup.ConfigModel.model_validate(
        {"target_id": str(TARGET), "name": "Photos", "env_file": "/etc/restic/photos.env", **extra}
    )


def _state(config: restic_backup.ConfigModel, result: ProbeResult) -> tuple[str, StateTone, str]:
    [state] = restic_backup.parse(config, result)
    return state.value, state.tone, state.detail


def test_build_offers_run_backup_only_with_a_unit() -> None:
    built = restic_backup.build(_config())
    assert built.actions == []
    assert [(t.state_key, t.label) for t in built.tiles] == [("last_backup", "Photos backup")]
    [backup] = restic_backup.build(_config(unit="restic-photos.service")).actions
    assert (backup.key, backup.name, backup.timeout_seconds) == ("backup", "Back up Photos", 3600)
    assert isinstance(backup.spec, ScriptSpec)
    assert backup.spec.env == {"UNIT": "restic-photos.service"}
    assert "restic-photos" not in backup.spec.script  # Config reaches scripts as env only.
    probe = restic_backup.probe(_config(snapshot_host="nas"))
    assert isinstance(probe.spec, ScriptSpec)
    assert probe.spec.env == {"ENV_FILE": "/etc/restic/photos.env", "SNAPSHOT_HOST": "nas"}


@pytest.mark.parametrize(
    "field",
    [
        {"env_file": "etc/restic.env"},
        {"env_file": "/etc/restic env"},
        {"env_file": "/etc/$(reboot)"},
        {"unit": "backup; reboot"},
        {"snapshot_host": "-rf"},
        {"max_age_hours": 0},
    ],
)
def test_bad_config_is_refused(field: dict) -> None:
    with pytest.raises(ValidationError):
        _config(**field)


def test_parse_ages_against_the_hosts_clock() -> None:
    config = _config(max_age_hours=24)
    hour = 3600

    def at(seconds_after: int) -> tuple[str, StateTone, str]:
        output = f"now {LATEST + seconds_after}\n{SNAPSHOTS}\n"
        return _state(config, ProbeResult(0, output))

    # The newest of the snapshots counts, whatever its path set.
    assert at(5 * 60) == ("up to date", StateTone.GOOD, "Last snapshot 5 min ago")
    assert at(23 * hour) == ("up to date", StateTone.GOOD, "Last snapshot 23 h ago")
    assert at(30 * hour) == ("late", StateTone.WARN, "Last snapshot 30 h ago")
    assert at(49 * hour) == ("overdue", StateTone.BAD, "Last snapshot 2 days ago")
    # A host clock slightly behind the snapshot is not "in the future".
    assert at(-30)[2] == "Last snapshot 0 min ago"


def test_parse_failures() -> None:
    config = _config(snapshot_host="nas")
    assert _state(config, ProbeResult(0, f"now {LATEST}\n[]\n")) == (
        "no backups",
        StateTone.BAD,
        "No snapshots of nas yet",
    )
    assert _state(config, ProbeResult(12, f"now {LATEST}\n{WRONG_PASSWORD}\n")) == (
        "error",
        StateTone.BAD,
        "Wrong restic password",
    )
    assert _state(config, ProbeResult(10, f"now {LATEST}\n{NO_REPOSITORY}\n")) == (
        "error",
        StateTone.BAD,
        "repository does not exist: unable to open config file: stat /nope/config: no such "
        "file or directory",
    )
    assert _state(config, ProbeResult(1, "now 1\nsudo: a password is required\n"))[2] == (
        "sudo: a password is required"
    )
    assert _state(config, ProbeResult(None, "", error="Host key changed")) == (
        "unknown",
        StateTone.UNKNOWN,
        "Host key changed",
    )
    assert _state(config, ProbeResult(0, f"now {LATEST}\n[{{}}]\n"))[0] == "unknown"


def _host(tmp_path: Path, restic: str) -> dict[str, str]:
    """A PATH with a stand-in restic and a sudo that just runs its command."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in {"restic": restic, "sudo": '[ "$1" = -n ] && shift\nexec "$@"\n'}.items():
        path = bin_dir / name
        path.write_text(f"#!/bin/sh\n{body}")
        path.chmod(0o755)
    return {"PATH": f"{bin_dir}:/usr/bin:/bin"}


def _probe(config: restic_backup.ConfigModel, env: dict[str, str]) -> ProbeResult:
    spec = restic_backup.probe(config).spec
    assert isinstance(spec, ScriptSpec)
    result = subprocess.run(  # noqa: S603 - the feature's own fixed script
        ["/bin/sh", "-c", spec.script],
        env={**os.environ, **env, **spec.env},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return ProbeResult(result.returncode, result.stdout + result.stderr)


def test_probe_loads_the_settings_file_and_filters_by_host(tmp_path: Path) -> None:
    settings = tmp_path / "photos.env"
    settings.write_text("RESTIC_REPOSITORY=sftp:nas:/srv/restic\nRESTIC_PASSWORD=hunter2\n")
    restic = (
        'echo "repo=$RESTIC_REPOSITORY password=$RESTIC_PASSWORD args=$*" >&2\n'
        f"echo '{SNAPSHOTS}'\n"
    )
    env = _host(tmp_path, restic)
    config = _config(env_file=str(settings), snapshot_host="nas")
    result = _probe(config, env)
    assert result.exit_code == 0, result.output
    assert (
        "repo=sftp:nas:/srv/restic password=hunter2 args=--no-lock snapshots --json "
        "--latest 1 --host nas"
    ) in result.output
    assert _state(config, result)[:2] == ("up to date", StateTone.GOOD)
    # Without a host filter, no --host argument at all.
    assert result.output.count("--host") == 1
    every = _probe(_config(env_file=str(settings)), env)
    assert "--latest 1\n" in every.output


def test_probe_explains_a_missing_settings_file_or_restic(tmp_path: Path) -> None:
    env = _host(tmp_path, "exit 0\n")
    missing = _probe(_config(env_file=str(tmp_path / "none.env")), env)
    assert missing.exit_code == 4
    assert _state(_config(), missing)[2] == f"Cannot read the settings file {tmp_path}/none.env"
    (tmp_path / "bin" / "restic").unlink()
    settings = tmp_path / "s.env"
    settings.write_text("")
    no_restic = _probe(_config(env_file=str(settings)), {"PATH": f"{tmp_path}/bin:/bin"})
    assert no_restic.exit_code == 3
    assert _state(_config(), no_restic)[2] == "restic is not installed on this host"
