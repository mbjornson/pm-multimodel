from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .adapters import (
    MARKER,
    adapt_codex_prompt,
    adapt_command,
    adapt_skill,
    codex_agents_adapter,
    cursor_rule_adapter,
    digest,
)


@dataclass
class Operation:
    action: str
    destination: Path
    source: Path | None = None
    content: str | None = None
    reason: str = ""


@dataclass
class Report:
    operations: list[Operation] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts


def default_home() -> Path:
    return Path(os.environ.get("PM_MULTIMODELS_HOME", Path.home() / ".pm-multimodels"))


def is_managed_file(path: Path) -> bool:
    try:
        return path.is_file() and MARKER in path.read_text(errors="ignore")
    except OSError:
        return False


def same_symlink(path: Path, target: Path) -> bool:
    if not path.is_symlink():
        return False
    return (path.parent / os.readlink(path)).resolve() == target.resolve()


def tree_digest(root: Path) -> str:
    entries: list[bytes] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        entries.append(str(path.relative_to(root)).encode())
        entries.append(path.read_bytes())
    return digest(b"\0".join(entries))


class SyncEngine:
    def __init__(self, home: Path | None = None, user_home: Path | None = None):
        self.home = (home or default_home()).expanduser()
        self.user_home = (user_home or Path.home()).expanduser()
        self.cache = self.home / "generated"
        self._known_hashes: dict[str, str] = {}
        self._backup_root = self.home / "backups"

    def configure(
        self,
        repo: Path,
        *,
        mode: str = "symlink",
        include_global: bool = False,
        adopt_agents: bool = False,
        update_gitignore: bool = False,
        apply: bool = False,
    ) -> Report:
        repo = repo.expanduser().resolve()
        report = Report()
        from . import updater
        update_command = f'python3 "{updater.plugin_root() / "scripts" / "pm-multimodels"}"'
        claude = repo / "CLAUDE.md"
        if not claude.is_file():
            report.conflicts.append(f"Missing canonical source: {claude}")
            return report
        if mode not in {"symlink", "copy"}:
            report.conflicts.append(f"Unsupported mode: {mode}")
            return report

        state_dir = repo / ".pm-multimodels"
        generated = state_dir / "generated"
        config = repo / ".pm-multimodels.json"
        agents = repo / "AGENTS.md"
        cursor_rule = repo / ".cursor/rules/999-pm-multimodels.mdc"
        self._known_hashes = self._load_hashes(state_dir / "manifest.json")
        self._backup_root = state_dir / "backups"

        self._plan_file(
            report,
            agents,
            codex_agents_adapter(claude, update_command),
            allow_replace=adopt_agents,
            reason="Codex project adapter",
        )
        self._plan_file(report, cursor_rule, cursor_rule_adapter(claude, update_command), reason="Cursor tool adapter")

        skill_sources = self._skill_sources(repo / ".claude/skills")
        command_root = repo / ".claude/commands"
        command_sources = self._command_sources(command_root)
        for platform in ("codex", "cursor"):
            for source in skill_sources:
                name, content = adapt_skill(source, platform)
                cache_dir = generated / platform / "skills" / name
                destination = (
                    repo / ".agents/skills" / name
                    if platform == "codex"
                    else repo / ".cursor/skills" / name
                )
                self._plan_generated_tree(report, source.parent, cache_dir, destination, content, mode)

            for source in command_sources:
                command_name = self._relative_command_name(source, command_root)
                name, content = adapt_command(source, platform, command_name)
                if platform == "codex":
                    cache_dir = generated / platform / "commands" / name
                    destination = repo / ".agents/skills" / name
                    self._plan_generated_tree(report, source, cache_dir, destination, content, mode)
                else:
                    destination = repo / ".cursor/commands" / f"{name}.md"
                    self._plan_file(report, destination, content, reason=f"Cursor command from {source}")

        ignored = self._ignored_cursor_outputs(repo)
        if ignored:
            message = "Cursor outputs are ignored by .gitignore: " + ", ".join(ignored)
            if update_gitignore:
                self._plan_gitignore(report, repo / ".gitignore")
            else:
                report.warnings.append(message + "; use --update-gitignore to expose them to Git")

        config_content = json.dumps(
            {
                "schema": 1,
                "generated_by": "pm-multimodels",
                "canonical": "CLAUDE.md",
                "mode": mode,
                "include_global": include_global,
            },
            indent=2,
        ) + "\n"
        self._plan_config(report, config, config_content)

        if include_global:
            global_report = self.sync_global(apply=False)
            report.operations.extend(global_report.operations)
            report.conflicts.extend(global_report.conflicts)
            report.warnings.extend(global_report.warnings)

        self._add_collision_conflicts(report)
        if apply and report.ok:
            self._apply(report)
            self._write_manifest(repo, report)
            self._register_repo(repo)
            if include_global:
                self.sync_global(apply=True)
        return report

    def sync_repo(self, repo: Path, *, apply: bool = False) -> Report:
        config_path = repo.expanduser().resolve() / ".pm-multimodels.json"
        if not config_path.is_file():
            report = Report()
            report.conflicts.append(f"Repository is not configured: {config_path}")
            return report
        payload = json.loads(config_path.read_text())
        return self.configure(
            repo,
            mode=payload.get("mode", "symlink"),
            include_global=payload.get("include_global", False),
            apply=apply,
        )

    def sync_global(self, *, apply: bool = False) -> Report:
        report = Report()
        self._known_hashes = self._load_hashes(self.home / "manifest.json")
        self._backup_root = self.home / "backups"
        claude_root = self.user_home / ".claude"
        skill_sources = self._skill_sources(claude_root / "skills")
        command_root = claude_root / "commands"
        command_sources = self._command_sources(command_root)

        for platform in ("codex", "cursor"):
            for source in skill_sources:
                name, content = adapt_skill(source, platform)
                cache_dir = self.cache / platform / "skills" / name
                destination = (
                    self.user_home / ".agents/skills" / name
                    if platform == "codex"
                    else self.user_home / ".cursor/skills" / name
                )
                self._plan_generated_tree(
                    report, source.parent, cache_dir, destination, content, "symlink"
                )

            for source in command_sources:
                command_name = self._relative_command_name(source, command_root)
                name, content = adapt_command(source, platform, command_name)
                if platform == "codex":
                    cache_dir = self.cache / platform / "commands" / name
                    destination = self.user_home / ".agents/skills" / name
                    self._plan_generated_tree(
                        report, source, cache_dir, destination, content, "symlink"
                    )
                    prompt = self.user_home / ".codex/prompts" / f"{command_name}.md"
                    self._plan_file(
                        report,
                        prompt,
                        adapt_codex_prompt(source),
                        reason=f"Codex prompt from {source}",
                    )
                else:
                    destination = self.user_home / ".cursor/commands" / f"{name}.md"
                    self._plan_file(report, destination, content, reason=f"Cursor command from {source}")

        self._add_collision_conflicts(report)
        if apply and report.ok:
            self._apply(report)
            self._write_global_manifest(report)
        return report

    def doctor(self, repo: Path | None = None) -> Report:
        report = Report()
        for source in (
            self.user_home / ".claude/skills",
            self.user_home / ".claude/commands",
        ):
            if not source.exists():
                report.warnings.append(f"Source directory does not exist: {source}")
        if repo:
            repo = repo.expanduser().resolve()
            if not (repo / "CLAUDE.md").is_file():
                report.conflicts.append(f"Missing canonical source: {repo / 'CLAUDE.md'}")
            if not (repo / ".pm-multimodels.json").is_file():
                report.warnings.append(f"Repository is not configured: {repo}")
        for root in (self.user_home / ".agents/skills", self.user_home / ".cursor/skills"):
            if root.exists():
                for path in root.iterdir():
                    if path.is_symlink() and not path.exists():
                        report.conflicts.append(f"Broken symlink: {path}")
        return report

    def registered_repos(self) -> list[Path]:
        registry = self.home / "config.json"
        if not registry.is_file():
            return []
        data = json.loads(registry.read_text())
        return [Path(value) for value in data.get("repositories", [])]

    def source_fingerprint(self) -> str:
        entries: list[str] = []
        roots = [
            self.user_home / ".claude/skills",
            self.user_home / ".claude/commands",
        ]
        for repo in self.registered_repos():
            roots.extend(
                [
                    repo / "CLAUDE.md",
                    repo / ".claude/skills",
                    repo / ".claude/commands",
                ]
            )
        for root in roots:
            if root.is_file():
                stat = root.stat()
                entries.append(f"{root}:{stat.st_mtime_ns}:{stat.st_size}")
                continue
            if root.exists():
                for path in sorted(p for p in root.rglob("*") if p.is_file()):
                    stat = path.stat()
                    entries.append(f"{path}:{stat.st_mtime_ns}:{stat.st_size}")
        return digest("\n".join(entries))

    @staticmethod
    def _skill_sources(root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        return sorted(path for path in root.rglob("SKILL.md") if path.is_file())

    @staticmethod
    def _command_sources(root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        return sorted(path for path in root.rglob("*.md") if path.is_file())

    @staticmethod
    def _relative_command_name(source: Path, root: Path) -> str:
        relative = source.relative_to(root).with_suffix("")
        return "-".join(relative.parts)

    @staticmethod
    def _add_collision_conflicts(report: Report) -> None:
        destinations: dict[Path, list[Operation]] = {}
        for operation in report.operations:
            if operation.action not in {"write", "generate-tree", "symlink"}:
                continue
            destinations.setdefault(operation.destination, []).append(operation)
        for destination, operations in destinations.items():
            if len(operations) > 1:
                sources = ", ".join(
                    str(operation.source or "<generated>") for operation in operations
                )
                report.conflicts.append(
                    f"Multiple sources map to {destination}: {sources}"
                )

    def _plan_file(
        self,
        report: Report,
        destination: Path,
        content: str,
        *,
        allow_replace: bool = False,
        reason: str = "",
    ) -> None:
        if destination.is_symlink():
            report.conflicts.append(f"Expected managed file but found symlink: {destination}")
            return
        if destination.exists() and not is_managed_file(destination) and not allow_replace:
            report.conflicts.append(f"Unmanaged destination exists: {destination}")
            return
        if destination.exists() and not is_managed_file(destination) and allow_replace:
            backup = self._backup_root / f"{destination.name}.bak"
            report.operations.append(Operation("backup", backup, source=destination))
        known_hash = self._known_hashes.get(str(destination))
        if (
            destination.is_file()
            and is_managed_file(destination)
            and known_hash
            and digest(destination.read_bytes()) != known_hash
        ):
            report.conflicts.append(f"Managed destination was modified: {destination}")
            return
        if destination.is_file() and destination.read_text() == content:
            return
        report.operations.append(Operation("write", destination, content=content, reason=reason))

    def _plan_generated_tree(
        self,
        report: Report,
        source_dir: Path,
        cache_dir: Path,
        destination: Path,
        skill_content: str,
        mode: str,
    ) -> None:
        if mode == "symlink":
            if destination.exists() or destination.is_symlink():
                if not same_symlink(destination, cache_dir):
                    report.conflicts.append(f"Unmanaged destination exists: {destination}")
                    return
            report.operations.append(
                Operation("generate-tree", cache_dir, source=source_dir, content=skill_content)
            )
            if not same_symlink(destination, cache_dir):
                report.operations.append(Operation("symlink", destination, source=cache_dir))
        else:
            skill_file = destination / "SKILL.md"
            if destination.exists() and not is_managed_file(skill_file):
                report.conflicts.append(f"Unmanaged destination exists: {destination}")
                return
            known_hash = self._known_hashes.get(str(destination))
            if (
                skill_file.is_file()
                and known_hash
                and tree_digest(destination) != known_hash
            ):
                report.conflicts.append(f"Managed destination was modified: {destination}")
                return
            report.operations.append(
                Operation("generate-tree", destination, source=source_dir, content=skill_content)
            )

    @staticmethod
    def _plan_config(report: Report, destination: Path, content: str) -> None:
        if destination.exists():
            try:
                current = json.loads(destination.read_text())
            except json.JSONDecodeError:
                report.conflicts.append(f"Invalid repository configuration: {destination}")
                return
            if current.get("generated_by") != "pm-multimodels":
                report.conflicts.append(f"Unmanaged destination exists: {destination}")
                return
            if destination.read_text() == content:
                return
        report.operations.append(
            Operation("write", destination, content=content, reason="Repository configuration")
        )

    @staticmethod
    def _ignored_cursor_outputs(repo: Path) -> list[str]:
        gitignore = repo / ".gitignore"
        if not gitignore.is_file():
            return []
        text = gitignore.read_text()
        if "/.cursor/*" not in text:
            return []
        ignored = []
        if "!/.cursor/skills/" not in text:
            ignored.append(".cursor/skills")
        if "!/.cursor/commands/" not in text:
            ignored.append(".cursor/commands")
        return ignored

    def _plan_gitignore(self, report: Report, path: Path) -> None:
        current = path.read_text() if path.exists() else ""
        additions = "\n# pm-multimodels generated Cursor configuration\n!/.cursor/skills/\n!/.cursor/skills/**\n!/.cursor/commands/\n!/.cursor/commands/**\n"
        if "!/.cursor/skills/" not in current or "!/.cursor/commands/" not in current:
            report.operations.append(
                Operation("write", path, content=current.rstrip() + additions, reason="Git visibility")
            )

    def _apply(self, report: Report) -> None:
        for operation in report.operations:
            if operation.action == "write":
                self._atomic_write(operation.destination, operation.content or "")
            elif operation.action == "generate-tree":
                self._generate_tree(
                    operation.source or Path(),
                    operation.destination,
                    operation.content or "",
                )
            elif operation.action == "symlink":
                operation.destination.parent.mkdir(parents=True, exist_ok=True)
                operation.destination.symlink_to(operation.source or Path(), target_is_directory=True)
            elif operation.action == "backup":
                operation.destination.parent.mkdir(parents=True, exist_ok=True)
                source = operation.source or Path()
                if source.is_dir():
                    if operation.destination.exists():
                        shutil.rmtree(operation.destination)
                    shutil.copytree(source, operation.destination)
                else:
                    shutil.copy2(source, operation.destination)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
            handle.write(content)
            temp = Path(handle.name)
        temp.replace(path)

    def _generate_tree(self, source: Path, destination: Path, skill_content: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
        try:
            if source.is_dir():
                for child in source.iterdir():
                    if child.name == "SKILL.md":
                        continue
                    target = temp / child.name
                    if child.is_dir():
                        shutil.copytree(child, target)
                    else:
                        shutil.copy2(child, target)
            (temp / "SKILL.md").write_text(skill_content)
            if destination.exists():
                shutil.rmtree(destination)
            temp.replace(destination)
        finally:
            if temp.exists():
                shutil.rmtree(temp)

    def _write_manifest(self, repo: Path, report: Report) -> None:
        entries = {
            destination: {"destination": destination, "hash": hash_value}
            for destination, hash_value in self._known_hashes.items()
        }
        for op in report.operations:
            entries[str(op.destination)] = {
                "action": op.action,
                "destination": str(op.destination),
                "source": str(op.source) if op.source else None,
                "hash": self._operation_hash(op),
            }
        manifest = {
            "schema": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "operations": list(entries.values()),
        }
        self._atomic_write(
            repo / ".pm-multimodels/manifest.json",
            json.dumps(manifest, indent=2) + "\n",
        )

    def _write_global_manifest(self, report: Report) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        entries = {
            destination: {"destination": destination, "hash": hash_value}
            for destination, hash_value in self._known_hashes.items()
        }
        for op in report.operations:
            entries[str(op.destination)] = {
                "action": op.action,
                "destination": str(op.destination),
                "source": str(op.source) if op.source else None,
                "hash": self._operation_hash(op),
            }
        payload = {
            "schema": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "operations": list(entries.values()),
        }
        self._atomic_write(
            self.home / "manifest.json", json.dumps(payload, indent=2) + "\n"
        )

    def _register_repo(self, repo: Path) -> None:
        registry = self.home / "config.json"
        data = json.loads(registry.read_text()) if registry.is_file() else {"schema": 1}
        repos = set(data.get("repositories", []))
        repos.add(str(repo))
        data["repositories"] = sorted(repos)
        self._atomic_write(registry, json.dumps(data, indent=2) + "\n")

    @staticmethod
    def _load_hashes(path: Path) -> dict[str, str]:
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            entry["destination"]: entry["hash"]
            for entry in data.get("operations", [])
            if entry.get("destination") and entry.get("hash")
        }

    @staticmethod
    def _operation_hash(operation: Operation) -> str | None:
        if operation.action == "write" and operation.destination.is_file():
            return digest(operation.destination.read_bytes())
        if operation.action == "generate-tree":
            if operation.destination.is_dir():
                return tree_digest(operation.destination)
        return None
