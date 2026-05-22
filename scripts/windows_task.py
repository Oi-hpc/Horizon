"""Manage the Windows scheduled task for running Horizon daily.

Examples:
  python scripts/windows_task.py create
  python scripts/windows_task.py create --time 05:00 --enable-wake-timers
  python scripts/windows_task.py status
  python scripts/windows_task.py run
  python scripts/windows_task.py delete
"""

from __future__ import annotations

import argparse
import base64
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Sequence
from xml.sax.saxutils import escape


DEFAULT_TASK_NAME = "Horizon Daily"
DEFAULT_TIME = "05:00"
TASK_XML_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def main() -> int:
    if os.name != "nt":
        print("This script only manages Windows scheduled tasks.", file=sys.stderr)
        return 2

    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "create":
            return create_task(args)
        if args.command == "delete":
            return delete_task(args.task_name)
        if args.command == "status":
            return status_task(args.task_name)
        if args.command == "run":
            return run_task(args.task_name)
        if args.command == "enable-wake-timers":
            return set_wake_timers(enabled=True, include_battery=args.battery)
        if args.command == "disable-wake-timers":
            return set_wake_timers(enabled=False, include_battery=args.battery)
        if args.command == "wake-status":
            return wake_timer_status()
    except subprocess.CalledProcessError as exc:
        print_command_error(exc)
        return exc.returncode or 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, inspect, run, or delete the Horizon Windows scheduled task."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", aliases=["install", "update"])
    create.add_argument("--task-name", default=DEFAULT_TASK_NAME)
    create.add_argument("--time", default=DEFAULT_TIME, help="Daily run time in HH:MM, local time.")
    create.add_argument(
        "--project",
        default=str(repo_root()),
        help="Horizon project directory. Defaults to the repository root.",
    )
    create.add_argument("--uv", default=None, help="Path to uv.exe. Defaults to PATH lookup.")
    create.add_argument(
        "--uv-args",
        default="run horizon",
        help='Arguments passed to uv. Default: "run horizon".',
    )
    create.add_argument(
        "--log",
        default=None,
        help="Log file path. Defaults to <project>\\data\\logs\\horizon-scheduled.log.",
    )
    create.add_argument(
        "--no-wake",
        action="store_true",
        help="Do not set WakeToRun on the scheduled task.",
    )
    create.add_argument(
        "--ac-only",
        action="store_true",
        help="Only start while on AC power.",
    )
    create.add_argument(
        "--execution-hours",
        type=int,
        default=4,
        help="Maximum task runtime before Windows may stop it.",
    )
    create.add_argument(
        "--enable-wake-timers",
        action="store_true",
        help="Also enable AC wake timers in the active Windows power plan.",
    )
    create.add_argument(
        "--battery-wake-timers",
        action="store_true",
        help="When used with --enable-wake-timers, enable wake timers on battery too.",
    )

    for name in ("delete", "status", "run"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--task-name", default=DEFAULT_TASK_NAME)

    wake_on = subparsers.add_parser("enable-wake-timers")
    wake_on.add_argument(
        "--battery",
        action="store_true",
        help="Also enable wake timers while on battery.",
    )

    wake_off = subparsers.add_parser("disable-wake-timers")
    wake_off.add_argument(
        "--battery",
        action="store_true",
        help="Also disable wake timers while on battery.",
    )

    subparsers.add_parser("wake-status")
    return parser


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def create_task(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    if not project.exists():
        raise FileNotFoundError(f"Project directory does not exist: {project}")

    uv_path = resolve_uv(args.uv)
    uv_args = parse_uv_args(args.uv_args)
    hh, mm = parse_time(args.time)
    log_path = Path(args.log).expanduser().resolve() if args.log else project / "data" / "logs" / "horizon-scheduled.log"

    ps_script = build_runner_powershell(
        project=project,
        uv_path=uv_path,
        uv_args=uv_args,
        log_path=log_path,
    )
    encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    action_args = f"-NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}"

    xml = build_task_xml(
        command=str(powershell),
        arguments=action_args,
        working_directory=str(project),
        start_boundary=f"{date.today().isoformat()}T{hh:02d}:{mm:02d}:00",
        wake_to_run=not args.no_wake,
        ac_only=args.ac_only,
        execution_hours=max(args.execution_hours, 1),
    )

    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as fh:
        fh.write(xml)
        xml_path = Path(fh.name)

    try:
        run_checked(["schtasks.exe", "/Create", "/TN", args.task_name, "/XML", str(xml_path), "/F"])
    finally:
        xml_path.unlink(missing_ok=True)

    if args.enable_wake_timers:
        set_wake_timers(enabled=True, include_battery=args.battery_wake_timers)

    print(f"Task created or updated: {args.task_name}")
    print(f"Schedule: daily at {hh:02d}:{mm:02d}")
    print(f"Command: {uv_path} {' '.join(uv_args)}")
    print(f"Project: {project}")
    print(f"Log: {log_path}")
    if not args.no_wake:
        print("WakeToRun: enabled on the scheduled task")
    return 0


def delete_task(task_name: str) -> int:
    run_checked(["schtasks.exe", "/Delete", "/TN", task_name, "/F"])
    print(f"Task deleted: {task_name}")
    return 0


def status_task(task_name: str) -> int:
    result = run_checked(["schtasks.exe", "/Query", "/TN", task_name, "/V", "/FO", "LIST"])
    print(result.stdout)
    return 0


def run_task(task_name: str) -> int:
    run_checked(["schtasks.exe", "/Run", "/TN", task_name])
    print(f"Task started: {task_name}")
    return 0


def set_wake_timers(enabled: bool, include_battery: bool) -> int:
    value = "1" if enabled else "0"
    run_checked(["powercfg.exe", "/SETACVALUEINDEX", "SCHEME_CURRENT", "SUB_SLEEP", "RTCWAKE", value])
    if include_battery:
        run_checked(["powercfg.exe", "/SETDCVALUEINDEX", "SCHEME_CURRENT", "SUB_SLEEP", "RTCWAKE", value])
    run_checked(["powercfg.exe", "/SETACTIVE", "SCHEME_CURRENT"])

    state = "enabled" if enabled else "disabled"
    target = "AC and battery" if include_battery else "AC"
    print(f"Wake timers {state} for {target} on the active power plan.")
    return 0


def wake_timer_status() -> int:
    result = run_checked(["powercfg.exe", "/QUERY", "SCHEME_CURRENT", "SUB_SLEEP", "RTCWAKE"])
    print(result.stdout)
    return 0


def resolve_uv(explicit: str | None) -> Path:
    candidate = explicit or shutil.which("uv")
    if not candidate:
        raise FileNotFoundError("Could not find uv on PATH. Pass --uv C:\\path\\to\\uv.exe.")

    path = Path(candidate).expanduser()
    if not path.is_absolute():
        resolved = shutil.which(str(path))
        if not resolved:
            raise FileNotFoundError(f"Could not resolve uv path: {candidate}")
        path = Path(resolved)

    if not path.exists():
        raise FileNotFoundError(f"uv path does not exist: {path}")
    return path.resolve()


def parse_uv_args(raw: str) -> list[str]:
    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid --uv-args: {raw}") from exc
    if not parts:
        raise ValueError("--uv-args must not be empty")
    return parts


def parse_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise ValueError("Time must be HH:MM, for example 05:00") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Time must be a valid 24-hour HH:MM value")
    return hour, minute


def build_runner_powershell(
    project: Path,
    uv_path: Path,
    uv_args: Sequence[str],
    log_path: Path,
) -> str:
    args_array = ", ".join(ps_quote(arg) for arg in uv_args)
    return "\n".join(
        [
            "$ErrorActionPreference = 'Continue'",
            f"$project = {ps_quote(str(project))}",
            f"$uv = {ps_quote(str(uv_path))}",
            f"$uvArgs = @({args_array})",
            f"$log = {ps_quote(str(log_path))}",
            "$logDir = Split-Path -Parent $log",
            "New-Item -ItemType Directory -Force -LiteralPath $logDir | Out-Null",
            "Add-Content -LiteralPath $log -Value (\"`n===== Horizon started {0} =====\" -f (Get-Date -Format o))",
            "Set-Location -LiteralPath $project",
            "& $uv @uvArgs *>> $log",
            "$code = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }",
            "Add-Content -LiteralPath $log -Value (\"===== Horizon finished {0} exit={1} =====\" -f (Get-Date -Format o), $code)",
            "exit $code",
        ]
    )


def build_task_xml(
    command: str,
    arguments: str,
    working_directory: str,
    start_boundary: str,
    wake_to_run: bool,
    ac_only: bool,
    execution_hours: int,
) -> str:
    wake = bool_text(wake_to_run)
    disallow_battery = bool_text(ac_only)
    stop_on_battery = bool_text(ac_only)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="{TASK_XML_NAMESPACE}">
  <RegistrationInfo>
    <Description>Run Horizon daily via uv.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{escape(start_boundary)}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>{disallow_battery}</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>{stop_on_battery}</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>{wake}</WakeToRun>
    <ExecutionTimeLimit>PT{execution_hours}H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(working_directory)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_checked(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def print_command_error(exc: subprocess.CalledProcessError) -> None:
    command = " ".join(str(part) for part in exc.cmd)
    print(f"Command failed ({exc.returncode}): {command}", file=sys.stderr)
    if exc.stdout:
        print(exc.stdout, file=sys.stderr)
    if exc.stderr:
        print(exc.stderr, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
