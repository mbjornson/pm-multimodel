from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

from .engine import Report, SyncEngine


def print_report(report: Report, *, dry_run: bool) -> int:
    label = "PLAN" if dry_run else "APPLIED"
    for operation in report.operations:
        source = f" <- {operation.source}" if operation.source else ""
        print(f"{label} {operation.action}: {operation.destination}{source}")
    for warning in report.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for conflict in report.conflicts:
        print(f"CONFLICT: {conflict}", file=sys.stderr)
    if not report.operations and report.ok:
        print("No changes required.")
    return 0 if report.ok else 2


def install_launch_agent(script: Path, interval: float, engine: SyncEngine) -> int:
    if sys.platform != "darwin":
        print("--install-launch-agent is currently supported only on macOS", file=sys.stderr)
        return 2
    label = "com.pm-multimodels.watch"
    agents = Path.home() / "Library/LaunchAgents"
    plist_path = agents / f"{label}.plist"
    log_dir = engine.home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": label,
        "ProgramArguments": [
            sys.executable,
            str(script),
            "watch",
            "--interval",
            str(interval),
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_dir / "watch.stdout.log"),
        "StandardErrorPath": str(log_dir / "watch.stderr.log"),
    }
    agents.mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as handle:
        plistlib.dump(payload, handle)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(plist_path)], check=False)
    result = subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist_path)], check=False
    )
    if result.returncode:
        print(f"Created {plist_path}, but launchctl bootstrap failed", file=sys.stderr)
        return result.returncode
    print(f"Installed and started {plist_path}")
    return 0


def run_watch(engine: SyncEngine, interval: float) -> int:
    previous = ""
    print("Watching global Claude skills and commands. Press Ctrl-C to stop.", flush=True)
    try:
        while True:
            current = engine.source_fingerprint()
            if current != previous:
                report = engine.sync_global(apply=True)
                print_report(report, dry_run=False)
                for repo in engine.registered_repos():
                    print_report(engine.sync_repo(repo, apply=True), dry_run=False)
                previous = current
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="pm-multimodels",
        description="Synchronize Claude Code configuration to Codex and Cursor.",
    )
    sub = result.add_subparsers(dest="command", required=True)

    configure = sub.add_parser("configure")
    configure.add_argument("repo", type=Path)
    configure.add_argument("--mode", choices=("symlink", "copy"), default="symlink")
    configure.add_argument("--include-global", action="store_true")
    configure.add_argument("--adopt-agents", action="store_true")
    configure.add_argument("--update-gitignore", action="store_true")
    configure.add_argument("--apply", action="store_true")

    sync = sub.add_parser("sync")
    sync.add_argument("repo", type=Path, nargs="?")
    sync.add_argument("--global", dest="global_sync", action="store_true")
    sync.add_argument("--apply", action="store_true")

    doctor = sub.add_parser("doctor")
    doctor.add_argument("repo", type=Path, nargs="?")

    watch = sub.add_parser("watch")
    watch.add_argument("--interval", type=float, default=2.0)
    watch.add_argument("--install-launch-agent", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    engine = SyncEngine()
    if args.command == "configure":
        report = engine.configure(
            args.repo,
            mode=args.mode,
            include_global=args.include_global,
            adopt_agents=args.adopt_agents,
            update_gitignore=args.update_gitignore,
            apply=args.apply,
        )
        return print_report(report, dry_run=not args.apply)
    if args.command == "sync":
        if not args.global_sync and not args.repo:
            print("sync requires a repository path or --global", file=sys.stderr)
            return 2
        status = 0
        if args.global_sync:
            status = max(
                status,
                print_report(engine.sync_global(apply=args.apply), dry_run=not args.apply),
            )
        if args.repo:
            status = max(
                status,
                print_report(
                    engine.sync_repo(args.repo, apply=args.apply), dry_run=not args.apply
                ),
            )
        return status
    if args.command == "doctor":
        return print_report(engine.doctor(args.repo), dry_run=True)
    if args.install_launch_agent:
        script = Path(__file__).resolve().parents[2] / "scripts/pm-multimodels"
        return install_launch_agent(script, args.interval, engine)
    return run_watch(engine, args.interval)
