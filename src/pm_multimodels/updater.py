from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .engine import SyncEngine, default_home  # noqa: F401  (re-exported for callers/tests)

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
    try:
        parts = path.read_text().split()
        if len(parts) != 3:
            return None
        version, level, timestamp = parts
        return version, int(level), float(timestamp)
    except (ValueError, OSError):
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
    except (ValueError, OSError):
        return False
    return now - timestamp < ttl


def touch_check(home: Path, now: float) -> None:
    _atomic_write(home / "last-update-check", f"{now}\n")


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def git_fetch(root: Path) -> bool:
    try:
        _git(root, "fetch", "--quiet", "origin", "main")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def commits_behind(root: Path) -> int:
    result = _git(root, "rev-list", "--count", "HEAD..origin/main", check=False)
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def remote_version(root: Path) -> str:
    result = _git(root, "show", "origin/main:.claude-plugin/plugin.json", check=False)
    if result.returncode != 0:
        return read_version(root)
    try:
        return str(json.loads(result.stdout).get("version", "0.0.0"))
    except (json.JSONDecodeError, AttributeError, TypeError):
        return read_version(root)


def check(
    *,
    root: Path | None = None,
    home: Path | None = None,
    force: bool = False,
    now: float,
) -> str:
    root = root or plugin_root()
    home = home or default_home()

    marker = home / "just-upgraded-from"
    if marker.is_file():
        from_version = marker.read_text().strip()
        marker.unlink()
        return f"JUST_UPGRADED {from_version} {read_version(root)}"

    if not config_true(home, "update_check"):
        return ""
    if not force and cache_fresh(home, now):
        return ""
    if not git_fetch(root):
        return ""
    touch_check(home, now)
    if commits_behind(root) == 0:
        return ""
    remote = remote_version(root)
    if not force and snooze_active(home, remote, now):
        return ""
    return f"UPGRADE_AVAILABLE {read_version(root)} {remote}"


def upgrade(
    *,
    root: Path | None = None,
    home: Path | None = None,
    now: float,
    runner=subprocess.run,
) -> tuple[int, str]:
    root = root or plugin_root()
    home = home or default_home()
    old_version = read_version(root)
    head = _git(root, "rev-parse", "HEAD", check=False).stdout.strip()
    dirty = bool(_git(root, "status", "--porcelain", check=False).stdout.strip())
    stashed = False
    if dirty:
        stash_result = _git(root, "stash", check=False)
        stashed = stash_result.returncode == 0

    try:
        if not git_fetch(root):
            raise RuntimeError("git fetch failed")
        _git(root, "reset", "--hard", "origin/main")
    except (subprocess.CalledProcessError, RuntimeError, OSError) as error:
        if head:
            _git(root, "reset", "--hard", head, check=False)
        if stashed:
            _git(root, "stash", "pop", check=False)
        return 1, f"Upgrade failed ({error}); restored previous version."

    new_version = read_version(root)
    notes: list[str] = []

    if shutil.which("claude"):
        runner(["claude", "plugin", "marketplace", "update", "pm-multimodels"], check=False)
        runner(["claude", "plugin", "update", "pm-multimodels@pm-multimodels"], check=False)
    else:
        notes.append("claude CLI not found; skipped Claude plugin reinstall.")

    engine = SyncEngine()
    if engine.sync_global(apply=True).conflicts:
        notes.append("Global re-sync reported conflicts; run /pm-multimodels:sync --global.")
    for repo in engine.registered_repos():
        if engine.sync_repo(repo, apply=True).conflicts:
            notes.append(f"Re-sync conflict in {repo}; run /pm-multimodels:sync {repo}.")

    _atomic_write(home / "just-upgraded-from", f"{old_version}\n")
    for name in ("last-update-check", "update-snoozed"):
        path = home / name
        if path.is_file():
            path.unlink()
    if stashed:
        notes.append("Local changes were stashed; run `git stash pop` in the plugin dir.")

    log = ""
    if head:
        log = _git(root, "log", "--oneline", f"{head}..HEAD", check=False).stdout.strip()

    lines = [f"Upgraded pm-multimodels {old_version} -> {new_version}."]
    if log:
        lines.append("Changes:\n" + log)
    lines.extend(notes)
    return 0, "\n".join(lines)
