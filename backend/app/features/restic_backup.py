"""Show how old the latest restic backup is, and start the backup, over SSH.

restic needs its repository, password, and any storage credentials as environment variables.
They stay on the host, in the same file the backup job already uses (an EnvironmentFile of
its systemd unit, say), which the check reads as root. runpad never sees them.
"""

import json
from datetime import datetime

from pydantic import BaseModel, Field

from app.features.base import (
    AS_ROOT,
    ActionTemplate,
    Build,
    ButtonTemplate,
    Feature,
    Poll,
    Probe,
    ProbeResult,
    SshTargetId,
    StateValue,
    TileTemplate,
    button,
    tile,
)
from app.models import ButtonColor, Executor, StateTone
from app.schemas.actions import ScriptSpec


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Host",
        description="The SSH target with restic installed, usually the machine being backed "
        "up. Its user must be root, or allowed to use sudo without a password.",
    )
    name: str = Field(
        title="Backup name",
        description="Shown on the tile and the button, for example Photos.",
        min_length=1,
        max_length=40,
    )
    env_file: str = Field(
        title="Settings file",
        description="A file on the host setting RESTIC_REPOSITORY and RESTIC_PASSWORD_FILE "
        "(or RESTIC_PASSWORD), plus any storage credentials, one VAR=value per line: usually "
        "the EnvironmentFile your backup job already uses. Read as root; it never leaves "
        "the host.",
        pattern=r"^/[A-Za-z0-9._/@+-]{1,250}$",
    )
    max_age_hours: int = Field(
        default=26,
        title="Backed up at least every (hours)",
        description="The tile turns amber when the latest snapshot is older than this, and "
        "red at twice this. 26 suits a daily backup.",
        ge=1,
        le=24 * 90,
    )
    snapshot_host: str = Field(
        default="",
        title="Only snapshots of host (optional)",
        description="For a repository shared by several machines: the restic host name "
        "whose snapshots count. Empty counts every snapshot.",
        pattern=r"^([A-Za-z0-9][A-Za-z0-9._-]{0,62})?$",
    )
    unit: str = Field(
        default="",
        title="Backup systemd unit (optional)",
        description="The unit that runs the backup, for example restic-backup.service. "
        "Needed for the Run backup button.",
        pattern=r"^([A-Za-z0-9@._:-]{1,100})?$",
    )


# Runs restic as root with the settings file loaded. sudo resets the environment, so the
# file and host name travel as arguments, never in the script text.
_RESTIC = r"""root sh -c '
PATH="$PATH:/usr/local/bin"
command -v restic >/dev/null || { echo "restic is not installed on this host"; exit 3; }
[ -r "$1" ] || { echo "Cannot read the settings file $1"; exit 4; }
set -a; . "$1"; set +a
exec restic --no-lock snapshots --json --latest 1 ${2:+--host "$2"}
' sh "$ENV_FILE" "$SNAPSHOT_HOST"
"""

# Prints "now <epoch seconds>" from the host's clock, then restic's JSON: the latest
# snapshot of each host and path set, or {"message_type": "exit_error", ...} on failure.
SCRIPT = f'{AS_ROOT}echo "now $(date +%s)"\n{_RESTIC}'

RUN_BACKUP = (
    AS_ROOT
    + r"""echo "Starting $UNIT; this waits until the backup finishes."
if root systemctl start --wait "$UNIT"; then
  echo "Backup finished."
else
  code=$?
  echo "The backup failed. Its last log lines:"
  root journalctl -u "$UNIT" -n 30 --no-pager -o cat
  exit "$code"
fi
"""
)


def build(config: ConfigModel) -> Build:
    actions = []
    if config.unit:
        actions.append(
            ActionTemplate(
                key="backup",
                name=f"Back up {config.name}",
                description=f"Runs the {config.name} backup now and waits for it to finish. "
                "If that takes over an hour, the run stops waiting but the backup goes on.",
                executor=Executor.SSH,
                target_id=config.target_id,
                spec=ScriptSpec(script=RUN_BACKUP, env={"UNIT": config.unit}),
                timeout_seconds=3600,
                button=ButtonTemplate(label=f"Back up {config.name}", color=ButtonColor.SKY),
            )
        )
    return Build(
        actions=actions,
        tiles=[TileTemplate(state_key="last_backup", label=f"{config.name} backup")],
    )


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.SSH,
        target_id=config.target_id,
        spec=ScriptSpec(
            script=SCRIPT,
            env={"ENV_FILE": config.env_file, "SNAPSHOT_HOST": config.snapshot_host},
        ),
        timeout_seconds=120,
    )


def _age(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{max(minutes, 0)} min"
    if minutes < 48 * 60:
        return f"{minutes // 60} h"
    return f"{minutes // (24 * 60)} days"


def _restic_error(lines: list[str]) -> str | None:
    for line in lines:
        if line.startswith("{") and '"exit_error"' in line:
            try:
                message = str(json.loads(line).get("message", ""))
            except ValueError:
                continue
            return message.removeprefix("Fatal: ").splitlines()[0]
    return None


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    if result.error is not None:
        return [StateValue("last_backup", "unknown", StateTone.UNKNOWN, result.error)]
    now = next((int(w[1]) for w in (line.split() for line in lines) if w[:1] == ["now"]), None)
    listing = next((line for line in lines if line.startswith("[")), None)
    if result.exit_code != 0 or now is None or listing is None:
        detail = _restic_error(lines) or (lines[-1] if lines else "")
        if result.exit_code == 12:
            detail = "Wrong restic password"
        return [
            StateValue(
                "last_backup",
                "error",
                StateTone.BAD,
                detail or f"restic exited with {result.exit_code}",
            )
        ]
    try:
        snapshots = json.loads(listing)
        times = [datetime.fromisoformat(s["time"]) for s in snapshots]
    except (ValueError, KeyError, TypeError):
        return [
            StateValue("last_backup", "unknown", StateTone.UNKNOWN, "Unexpected answer from restic")
        ]
    if not times:
        whose = f" of {config.snapshot_host}" if config.snapshot_host else ""
        return [StateValue("last_backup", "no backups", StateTone.BAD, f"No snapshots{whose} yet")]
    age = now - max(times).timestamp()
    limit = config.max_age_hours * 3600
    detail = f"Last snapshot {_age(age)} ago"
    if age <= limit:
        return [StateValue("last_backup", "up to date", StateTone.GOOD, detail)]
    if age <= 2 * limit:
        return [StateValue("last_backup", "late", StateTone.WARN, detail)]
    return [StateValue("last_backup", "overdue", StateTone.BAD, detail)]


FEATURE = Feature(
    id="restic_backup",
    name="restic backup",
    description="See how old the latest restic snapshot is (amber when late, red when "
    "overdue), and run the backup.",
    icon="backup",
    category="Storage",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        button("backup", "Run backup", "Runs the backup's systemd unit and waits for it."),
        tile("last_backup", "Last backup", "Up to date, late, or overdue, by the latest snapshot."),
    ],
    poll=Poll(probe=probe, parse=parse, interval_seconds=600),
)
