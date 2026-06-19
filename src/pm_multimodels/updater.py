from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .engine import default_home  # noqa: F401  (re-exported for callers/tests)

DEFAULTS: dict[str, str] = {"auto_upgrade": "false", "update_check": "true"}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp = Path(handle.name)
    temp.replace(path)


def plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def read_version(root: Path) -> str:
    data = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
    return str(data.get("version", "0.0.0"))


def _config_path(home: Path) -> Path:
    return home / "config"


def _read_config(home: Path) -> dict[str, str]:
    path = _config_path(home)
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            values[key.strip()] = value.strip()
    return values


def config_get(home: Path, key: str) -> str:
    return _read_config(home).get(key, DEFAULTS.get(key, ""))


def config_set(home: Path, key: str, value: str) -> None:
    values = _read_config(home)
    values[key] = value
    body = "".join(f"{name}={values[name]}\n" for name in sorted(values))
    _atomic_write(_config_path(home), body)


def config_true(home: Path, key: str) -> bool:
    return config_get(home, key).lower() in {"true", "1", "yes"}
