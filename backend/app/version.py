"""runpad's version, from pyproject.toml (the one place it is set; release.sh checks it)."""

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _read() -> str:
    try:
        with _PYPROJECT.open("rb") as file:
            return str(tomllib.load(file)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "unknown"


VERSION = _read()
