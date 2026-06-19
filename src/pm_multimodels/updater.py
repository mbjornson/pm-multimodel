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


SNOOZE_DURATIONS: dict[int, int] = {1: 86400, 2: 172800, 3: 604800}
SNOOZE_LABELS: dict[int, str] = {1: "24h", 2: "48h", 3: "1 week"}
CHECK_TTL = 14400  # 4 hours


def _read_snooze(home: Path) -> tuple[str, int, float] | None:
    path = home / "update-snoozed"
    if not path.is_file():
        return None
    parts = path.read_text().split()
    if len(parts) != 3:
        return None
    version, level, timestamp = parts
    try:
        return version, int(level), float(timestamp)
    except ValueError:
        return None


def snooze(home: Path, version: str, now: float) -> str:
    current = _read_snooze(home)
    level = current[1] if current and current[0] == version else 0
    new_level = min(level + 1, 3)
    _atomic_write(home / "update-snoozed", f"{version} {new_level} {now}\n")
    return SNOOZE_LABELS[new_level]


def snooze_active(home: Path, version: str, now: float) -> bool:
    current = _read_snooze(home)
    if not current or current[0] != version:
        return False
    _, level, timestamp = current
    return now < timestamp + SNOOZE_DURATIONS.get(level, 0)


def cache_fresh(home: Path, now: float, ttl: float = CHECK_TTL) -> bool:
    path = home / "last-update-check"
    if not path.is_file():
        return False
    try:
        timestamp = float(path.read_text().strip())
    except ValueError:
        return False
    return now - timestamp < ttl


def touch_check(home: Path, now: float) -> None:
    _atomic_write(home / "last-update-check", f"{now}\n")
