#!/usr/bin/env python3
"""Run prepared VASP directories inside an already allocated compute node."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNNER_NAME = "vasp_local_node_runner"
DEFAULT_MAX_VASP_CORES = 40
STATE_FILE = ".mesa_vasp_local_state.json"
LOCK_FILE = ".mesa_vasp_local.lock"
READY_FILE = ".mesa_vasp_local_ready"
STARTED_FILE = ".mesa_vasp_local_started"
FINISHED_FILE = ".mesa_vasp_local_finished"
EXIT_CODE_FILE = ".mesa_vasp_local_exit_code"
STDOUT_LOG = "vasp.local.stdout"
STDERR_LOG = "vasp.local.stderr"
COMMAND_LOG = "vasp.local.command.json"
WATCH_STATE_FILE = ".mesa_vasp_local_watch.json"
LEGACY_FINISHED_FILE = ".vasp_submit_finished"
LEGACY_EXIT_CODE_FILE = ".vasp_submit_exit_code"
LEGACY_METADATA_FILE = ".vasp_submit_metadata.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def strip_incar_comment(line: str) -> str:
    for token in ("#", "!"):
        if token in line:
            line = line.split(token, 1)[0]
    return line.strip()


def incar_has_kspacing(incar_path: Path) -> bool:
    for raw_line in read_text(incar_path).splitlines():
        line = strip_incar_comment(raw_line).upper()
        if line.startswith("KSPACING") and "=" in line:
            return True
    return False


def input_status(job_dir: Path) -> dict[str, Any]:
    required = ["POSCAR", "INCAR", "POTCAR"]
    incar_path = job_dir / "INCAR"
    if not incar_path.exists() or not incar_has_kspacing(incar_path):
        required.append("KPOINTS")
    present = [name for name in required if (job_dir / name).is_file()]
    missing = [name for name in required if name not in present]
    return {
        "required": required,
        "present": present,
        "missing": missing,
        "ok": not missing,
    }


def parse_positive_int(value: Any, fallback: int | None = None) -> int | None:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def default_max_cores() -> int:
    return parse_positive_int(os.environ.get("MESA_VASP_MAX_CORES"), DEFAULT_MAX_VASP_CORES) or DEFAULT_MAX_VASP_CORES


def detected_cores(cli_cores: int | None) -> tuple[int, str]:
    if cli_cores:
        return cli_cores, "cli"
    for key in ("NSLOTS", "SLURM_NTASKS", "MESA_VASP_CORES"):
        parsed = parse_positive_int(os.environ.get(key))
        if parsed:
            return parsed, key
    return DEFAULT_MAX_VASP_CORES, "default"


def resolve_max_cores(cli_max_cores: int | None) -> int:
    return parse_positive_int(cli_max_cores, default_max_cores()) or DEFAULT_MAX_VASP_CORES


def resolve_cores(cli_cores: int | None, max_cores: int | None = None) -> int:
    raw_cores, _source = detected_cores(cli_cores)
    resolved_max = resolve_max_cores(max_cores)
    return min(raw_cores, resolved_max)


def core_policy(cli_cores: int | None, max_cores: int | None, resolved_cores: int) -> dict[str, Any]:
    raw_cores, source = detected_cores(cli_cores)
    resolved_max = resolve_max_cores(max_cores)
    return {
        "raw_cores": raw_cores,
        "raw_cores_source": source,
        "max_vasp_cores": resolved_max,
        "resolved_vasp_cores": resolved_cores,
        "capped": resolved_cores < raw_cores,
        "serial_calculations": True,
    }


def machinefile_path() -> Path | None:
    tmpdir = os.environ.get("TMPDIR")
    if tmpdir:
        candidate = Path(tmpdir) / "machines"
        if candidate.is_file():
            return candidate
    pe_hostfile = os.environ.get("PE_HOSTFILE")
    if pe_hostfile and Path(pe_hostfile).is_file():
        return Path(pe_hostfile)
    return None


def allocation_detected() -> bool:
    if os.environ.get("MESA_ALLOW_LOCAL_VASP") == "1":
        return True
    if os.environ.get("NSLOTS") or os.environ.get("SLURM_JOB_ID"):
        return True
    return machinefile_path() is not None


def allocation_context(cores: int) -> dict[str, Any]:
    machinefile = machinefile_path()
    return {
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "cwd": str(Path.cwd()),
        "cores": cores,
        "nslots": os.environ.get("NSLOTS"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "tmpdir": os.environ.get("TMPDIR"),
        "pe_hostfile": os.environ.get("PE_HOSTFILE"),
        "machinefile": str(machinefile) if machinefile else None,
        "allocation_detected": allocation_detected(),
    }


def resolve_executable(kind: str) -> str:
    if kind == "std":
        return os.environ.get("MESA_VASP_STD") or os.environ.get("VASP_STD") or "vasp_std"
    if kind == "gam":
        return os.environ.get("MESA_VASP_GAM") or os.environ.get("VASP_GAM") or "vasp_gam"
    if kind == "ncl":
        return os.environ.get("MESA_VASP_NCL") or os.environ.get("VASP_NCL") or "vasp_ncl"
    raise ValueError(f"Unsupported executable kind: {kind}")


def fill_command_template(template: str, *, cores: int, executable: str, job_dir: Path) -> list[str]:
    machinefile = machinefile_path()
    filled = template
    replacements = {
        "{cores}": str(cores),
        "{executable}": executable,
        "{job_dir}": str(job_dir),
        "{machinefile}": str(machinefile or ""),
    }
    for key, value in replacements.items():
        filled = filled.replace(key, value)
    filled = os.path.expandvars(filled)
    return shlex.split(filled)


def infer_launcher(requested: str, cores: int) -> str:
    if requested != "auto":
        return requested
    if machinefile_path() and os.environ.get("TMPDIR"):
        return "mpirun-machinefile"
    if os.environ.get("SLURM_JOB_ID"):
        return "srun"
    if cores > 1:
        return "mpirun"
    return "none"


def build_command(
    *,
    job_dir: Path,
    executable_kind: str,
    launcher: str,
    cores: int,
    command_template: str | None,
) -> tuple[list[str], dict[str, Any]]:
    executable = resolve_executable(executable_kind)
    if command_template:
        command = fill_command_template(command_template, cores=cores, executable=executable, job_dir=job_dir)
        return command, {
            "mode": "template",
            "executable": executable,
            "launcher": "custom",
            "template": command_template,
        }

    selected_launcher = infer_launcher(launcher, cores)
    machinefile = machinefile_path()
    if selected_launcher == "mpirun-machinefile":
        if machinefile is None:
            raise RuntimeError("mpirun-machinefile launcher requires $TMPDIR/machines or $PE_HOSTFILE")
        command = ["mpirun", "-machinefile", str(machinefile), "-n", str(cores), executable]
    elif selected_launcher == "mpirun":
        command = ["mpirun", "-n", str(cores), executable]
    elif selected_launcher == "srun":
        command = ["srun", "-n", str(cores), executable]
    elif selected_launcher == "none":
        command = [executable]
    else:
        raise RuntimeError(f"Unsupported launcher: {selected_launcher}")

    return command, {
        "mode": "assembled",
        "executable": executable,
        "launcher": selected_launcher,
        "machinefile": str(machinefile) if machinefile else None,
    }


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def active_lock(lock_path: Path) -> tuple[bool, dict[str, Any]]:
    info = read_json(lock_path)
    if not info:
        return True, {"reason": "unreadable_lock"}
    host = info.get("hostname")
    pid = parse_positive_int(info.get("pid"))
    if host and host != socket.gethostname():
        return True, info
    return bool(pid and pid_alive(pid)), info


def acquire_lock(job_dir: Path, *, force_stale_lock: bool) -> tuple[bool, dict[str, Any]]:
    lock_path = job_dir / LOCK_FILE
    if lock_path.exists():
        active, info = active_lock(lock_path)
        if active:
            return False, {"code": "active_lock", "lock": info}
        if not force_stale_lock:
            return False, {"code": "stale_lock", "lock": info}
        lock_path.unlink(missing_ok=True)

    payload = {
        "runner": RUNNER_NAME,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "started_at": now_iso(),
    }
    try:
        handle = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False, {"code": "lock_race", "lock": read_json(lock_path)}
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")
    return True, payload


def release_lock(job_dir: Path) -> None:
    lock_path = job_dir / LOCK_FILE
    info = read_json(lock_path)
    if parse_positive_int(info.get("pid")) == os.getpid():
        lock_path.unlink(missing_ok=True)


def update_legacy_metadata(job_dir: Path, state: dict[str, Any]) -> None:
    metadata_path = job_dir / LEGACY_METADATA_FILE
    if not metadata_path.exists():
        return
    metadata = read_json(metadata_path)
    if not metadata:
        return
    metadata["state"] = state.get("state")
    metadata["local_runner"] = {
        "runner": RUNNER_NAME,
        "state_file": str(job_dir / STATE_FILE),
        "finished_at": state.get("finished_at"),
        "returncode": state.get("returncode"),
        "hostname": state.get("hostname"),
    }
    write_json(metadata_path, metadata)
    index_path = metadata.get("index_path")
    if index_path:
        try:
            write_json(Path(str(index_path)).expanduser(), metadata)
        except OSError:
            pass


def base_state(job_dir: Path, cores: int, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "runner": RUNNER_NAME,
        "job_dir": str(job_dir),
        "hostname": socket.gethostname(),
        "allocation": allocation_context(cores),
        "core_policy": policy,
        "input_status": input_status(job_dir),
    }


def write_command_record(job_dir: Path, command: list[str], command_info: dict[str, Any]) -> None:
    write_json(
        job_dir / COMMAND_LOG,
        {
            "runner": RUNNER_NAME,
            "created_at": now_iso(),
            "command": command,
            "command_info": command_info,
        },
    )


def validate_run_environment(
    *,
    job_dir: Path,
    cores: int,
    min_cores: int,
    require_allocation: bool,
) -> dict[str, Any] | None:
    checks = input_status(job_dir)
    if not checks["ok"]:
        return {
            "ok": False,
            "state": "invalid",
            "error": "required VASP input files are missing",
            "input_status": checks,
        }
    if cores < min_cores:
        return {
            "ok": False,
            "state": "blocked",
            "error": f"resolved cores {cores} is below required minimum {min_cores}",
            "allocation": allocation_context(cores),
        }
    if require_allocation and not allocation_detected():
        return {
            "ok": False,
            "state": "blocked",
            "error": "no allocation environment detected; set NSLOTS/SLURM_JOB_ID or MESA_ALLOW_LOCAL_VASP=1",
            "allocation": allocation_context(cores),
        }
    return None


def serial_lock_path(args: argparse.Namespace) -> Path:
    raw_dir = args.serial_lock_dir or os.environ.get("MESA_VASP_LOCAL_SERIAL_LOCK_DIR")
    lock_dir = Path(str(raw_dir)).expanduser() if raw_dir else Path.home() / ".mesa_vasp_local_runner"
    return lock_dir / f"{socket.gethostname()}.serial.lock"


def acquire_serial_lock(args: argparse.Namespace) -> tuple[bool, Path | None, dict[str, Any] | None]:
    if not args.serial_allocation_lock:
        return True, None, None
    path = serial_lock_path(args)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        active, info = active_lock(path)
        if active:
            return False, path, {"code": "active_serial_lock", "lock": info}
        if not args.force_stale_lock:
            return False, path, {"code": "stale_serial_lock", "lock": info}
        path.unlink(missing_ok=True)

    payload = {
        "runner": RUNNER_NAME,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "started_at": now_iso(),
        "policy": "one VASP calculation at a time per local-node runner allocation",
    }
    try:
        handle = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False, path, {"code": "serial_lock_race", "lock": read_json(path)}
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")
    return True, path, payload


def release_serial_lock(path: Path | None) -> None:
    if path is None:
        return
    info = read_json(path)
    if parse_positive_int(info.get("pid")) == os.getpid():
        path.unlink(missing_ok=True)


def run_job(job_dir: Path, args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    job_dir = job_dir.expanduser().resolve()
    max_cores = resolve_max_cores(args.max_cores)
    cores = resolve_cores(args.cores, max_cores)
    policy = core_policy(args.cores, max_cores, cores)
    validation_error = validate_run_environment(
        job_dir=job_dir,
        cores=cores,
        min_cores=args.min_cores,
        require_allocation=args.require_allocation,
    )
    if validation_error:
        state = {**base_state(job_dir, cores, policy), **validation_error, "checked_at": now_iso()}
        write_json(job_dir / STATE_FILE, state)
        return state, 2

    try:
        command, command_info = build_command(
            job_dir=job_dir,
            executable_kind=args.executable,
            launcher=args.launcher,
            cores=cores,
            command_template=args.vasp_command,
        )
    except Exception as exc:  # noqa: BLE001 - runner must leave structured state.
        state = {
            **base_state(job_dir, cores, policy),
            "ok": False,
            "state": "blocked",
            "error": str(exc),
            "checked_at": now_iso(),
        }
        write_json(job_dir / STATE_FILE, state)
        return state, 2

    write_command_record(job_dir, command, command_info)

    if args.dry_run:
        state = {
            **base_state(job_dir, cores, policy),
            "ok": True,
            "state": "dry_run",
            "dry_run": True,
            "command": command,
            "command_info": command_info,
            "checked_at": now_iso(),
        }
        write_json(job_dir / STATE_FILE, state)
        return state, 0

    locked, lock_info = acquire_lock(job_dir, force_stale_lock=args.force_stale_lock)
    if not locked:
        state = {
            **base_state(job_dir, cores, policy),
            "ok": False,
            "state": "blocked",
            "error": "job directory is locked",
            "lock": lock_info,
            "checked_at": now_iso(),
        }
        write_json(job_dir / STATE_FILE, state)
        return state, 2

    serial_locked, serial_lock, serial_info = acquire_serial_lock(args)
    if not serial_locked:
        release_lock(job_dir)
        state = {
            **base_state(job_dir, cores, policy),
            "ok": False,
            "state": "blocked",
            "error": "another local-node VASP calculation is already active; run calculations serially",
            "serial_lock": serial_info,
            "checked_at": now_iso(),
        }
        write_json(job_dir / STATE_FILE, state)
        return state, 2

    started_at = now_iso()
    write_text(job_dir / STARTED_FILE, started_at)
    running_state = {
        **base_state(job_dir, cores, policy),
        "ok": True,
        "state": "running",
        "dry_run": False,
        "started_at": started_at,
        "command": command,
        "command_info": command_info,
        "serial_lock": str(serial_lock) if serial_lock else None,
        "stdout": str(job_dir / STDOUT_LOG),
        "stderr": str(job_dir / STDERR_LOG),
    }
    write_json(job_dir / STATE_FILE, running_state)

    try:
        with (job_dir / STDOUT_LOG).open("ab") as stdout, (job_dir / STDERR_LOG).open("ab") as stderr:
            completed = subprocess.run(
                command,
                cwd=job_dir,
                stdout=stdout,
                stderr=stderr,
                check=False,
                timeout=args.timeout_seconds,
            )
        returncode = completed.returncode
        error = None
    except subprocess.TimeoutExpired as exc:
        returncode = None
        error = f"VASP command timed out after {exc.timeout} seconds"
    except Exception as exc:  # noqa: BLE001 - always preserve failure metadata.
        returncode = None
        error = str(exc)
    finally:
        release_serial_lock(serial_lock)
        release_lock(job_dir)

    finished_at = now_iso()
    state_name = "finished" if returncode == 0 else "failed"
    write_text(job_dir / FINISHED_FILE, finished_at)
    write_text(job_dir / EXIT_CODE_FILE, "" if returncode is None else str(returncode))
    if args.write_vasp_submit_markers:
        write_text(job_dir / LEGACY_FINISHED_FILE, finished_at)
        write_text(job_dir / LEGACY_EXIT_CODE_FILE, "" if returncode is None else str(returncode))

    final_state = {
        **base_state(job_dir, cores, policy),
        "ok": returncode == 0,
        "state": state_name,
        "dry_run": False,
        "started_at": started_at,
        "finished_at": finished_at,
        "returncode": returncode,
        "error": error,
        "command": command,
        "command_info": command_info,
        "serial_lock": str(serial_lock) if serial_lock else None,
        "stdout": str(job_dir / STDOUT_LOG),
        "stderr": str(job_dir / STDERR_LOG),
    }
    write_json(job_dir / STATE_FILE, final_state)
    if args.write_vasp_submit_markers:
        update_legacy_metadata(job_dir, final_state)
    return final_state, 0 if returncode == 0 else 1


def status_job(job_dir: Path) -> dict[str, Any]:
    job_dir = job_dir.expanduser().resolve()
    state = read_json(job_dir / STATE_FILE)
    lock_path = job_dir / LOCK_FILE
    if lock_path.exists():
        active, info = active_lock(lock_path)
        if active:
            return {
                "ok": True,
                "runner": RUNNER_NAME,
                "job_dir": str(job_dir),
                "state": "running",
                "running": True,
                "finished": False,
                "lock": info,
                "input_status": input_status(job_dir),
                "state_file": str(job_dir / STATE_FILE),
            }

    if (job_dir / FINISHED_FILE).exists():
        exit_code = read_text(job_dir / EXIT_CODE_FILE).strip()
        return {
            "ok": True,
            "runner": RUNNER_NAME,
            "job_dir": str(job_dir),
            "state": "finished" if exit_code == "0" else "failed",
            "running": False,
            "finished": True,
            "exit_code": exit_code,
            "finished_at": read_text(job_dir / FINISHED_FILE).strip(),
            "input_status": input_status(job_dir),
            "state_file": str(job_dir / STATE_FILE),
            "metadata": state or None,
        }

    if state.get("state"):
        return {
            "ok": True,
            "runner": RUNNER_NAME,
            "job_dir": str(job_dir),
            "state": state.get("state"),
            "running": False,
            "finished": False,
            "input_status": input_status(job_dir),
            "state_file": str(job_dir / STATE_FILE),
            "metadata": state,
        }

    checks = input_status(job_dir)
    return {
        "ok": True,
        "runner": RUNNER_NAME,
        "job_dir": str(job_dir),
        "state": "prepared" if checks["ok"] else "invalid",
        "running": False,
        "finished": False,
        "input_status": checks,
        "state_file": str(job_dir / STATE_FILE),
    }


def mark_ready(job_dir: Path) -> dict[str, Any]:
    job_dir = job_dir.expanduser().resolve()
    checks = input_status(job_dir)
    if not checks["ok"]:
        return {
            "ok": False,
            "runner": RUNNER_NAME,
            "job_dir": str(job_dir),
            "state": "invalid",
            "error": "required VASP input files are missing",
            "input_status": checks,
        }
    write_text(job_dir / READY_FILE, now_iso())
    return {
        "ok": True,
        "runner": RUNNER_NAME,
        "job_dir": str(job_dir),
        "state": "ready",
        "ready_marker": str(job_dir / READY_FILE),
        "input_status": checks,
    }


def discover_jobs(queue_dir: Path, *, include_failed: bool = False) -> list[dict[str, Any]]:
    queue_dir = queue_dir.expanduser().resolve()
    records: list[dict[str, Any]] = []
    if not queue_dir.exists():
        return records
    for marker in sorted(queue_dir.rglob(READY_FILE)):
        job_dir = marker.parent
        status = status_job(job_dir)
        state = status.get("state")
        if state == "finished":
            continue
        if state == "failed" and not include_failed:
            continue
        records.append(
            {
                "job_dir": str(job_dir),
                "ready_marker": str(marker),
                "state": state,
                "input_status": status.get("input_status"),
            }
        )
    return records


def list_jobs(queue_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    jobs = discover_jobs(queue_dir, include_failed=args.include_failed)
    return {
        "ok": True,
        "runner": RUNNER_NAME,
        "queue_dir": str(queue_dir.expanduser().resolve()),
        "count": len(jobs),
        "jobs": jobs,
    }


def watch_jobs(queue_dir: Path, args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    queue_dir = queue_dir.expanduser().resolve()
    queue_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    processed: list[dict[str, Any]] = []
    failures = 0

    def write_watch_state(state: str, extra: dict[str, Any] | None = None) -> None:
        resolved_cores = resolve_cores(args.cores, args.max_cores)
        payload = {
            "schema_version": 1,
            "runner": RUNNER_NAME,
            "state": state,
            "queue_dir": str(queue_dir),
            "started_at": started_at,
            "updated_at": now_iso(),
            "processed_count": len(processed),
            "failures": failures,
            "allocation": allocation_context(resolved_cores),
            "core_policy": core_policy(args.cores, resolve_max_cores(args.max_cores), resolved_cores),
        }
        if extra:
            payload.update(extra)
        write_json(queue_dir / WATCH_STATE_FILE, payload)

    write_watch_state("watching")
    idle_started: float | None = None
    try:
        while True:
            candidates = discover_jobs(queue_dir, include_failed=args.include_failed)
            if not candidates:
                if args.once:
                    break
                if idle_started is None:
                    idle_started = time.monotonic()
                if args.idle_exit_after and time.monotonic() - idle_started >= args.idle_exit_after:
                    break
                write_watch_state("idle")
                time.sleep(args.poll_seconds)
                continue

            idle_started = None
            for candidate in candidates:
                if args.max_jobs is not None and len(processed) >= args.max_jobs:
                    break
                job_dir = Path(candidate["job_dir"])
                write_watch_state("running", {"current_job_dir": str(job_dir)})
                result, code = run_job(job_dir, args)
                processed.append(
                    {
                        "job_dir": str(job_dir),
                        "state": result.get("state"),
                        "returncode": result.get("returncode"),
                        "runner_exit_code": code,
                    }
                )
                if code != 0:
                    failures += 1
                    if args.exit_on_failure:
                        write_watch_state("failed")
                        return {
                            "ok": False,
                            "runner": RUNNER_NAME,
                            "queue_dir": str(queue_dir),
                            "state": "failed",
                            "processed": processed,
                            "failures": failures,
                        }, 1
            if args.once or (args.max_jobs is not None and len(processed) >= args.max_jobs):
                break
    except KeyboardInterrupt:
        write_watch_state("interrupted")
        return {
            "ok": False,
            "runner": RUNNER_NAME,
            "queue_dir": str(queue_dir),
            "state": "interrupted",
            "processed": processed,
            "failures": failures,
        }, 130

    final_state = "finished" if args.once or args.max_jobs is not None or args.idle_exit_after else "watching"
    write_watch_state(final_state)
    return {
        "ok": failures == 0,
        "runner": RUNNER_NAME,
        "queue_dir": str(queue_dir),
        "state": final_state,
        "processed": processed,
        "processed_count": len(processed),
        "failures": failures,
        "watch_state": str(queue_dir / WATCH_STATE_FILE),
    }, 0 if failures == 0 else 1


def add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cores", type=int, help="Requested MPI rank count. Defaults to NSLOTS, SLURM_NTASKS, MESA_VASP_CORES, then 40; capped by --max-cores.")
    parser.add_argument("--max-cores", type=int, default=default_max_cores(), help="Maximum VASP MPI ranks. Default 40 to reserve cores on a 48-core allocation for Codex/OS.")
    parser.add_argument("--min-cores", type=int, default=40, help="Minimum resolved core count required for actual execution.")
    parser.add_argument("--require-allocation", action="store_true", help="Require NSLOTS/SLURM allocation markers or MESA_ALLOW_LOCAL_VASP=1.")
    parser.add_argument("--executable", choices=["std", "gam", "ncl"], default="std", help="VASP executable family to run.")
    parser.add_argument("--launcher", choices=["auto", "mpirun-machinefile", "mpirun", "srun", "none"], default=os.environ.get("MESA_VASP_LAUNCHER", "auto"))
    parser.add_argument("--vasp-command", help="Full command template. Supports {cores}, {executable}, {job_dir}, {machinefile}.")
    parser.add_argument("--timeout-seconds", type=int, help="Optional wall-time cap for one local VASP command.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and write command metadata without running VASP.")
    parser.add_argument("--force-stale-lock", action="store_true", help="Remove a stale lock from the same host before running.")
    parser.add_argument("--serial-allocation-lock", action=argparse.BooleanOptionalAction, default=True, help="Allow only one local-node VASP calculation at a time for this user on this node.")
    parser.add_argument("--serial-lock-dir", type=Path, help="Directory for the per-node serial execution lock.")
    parser.add_argument("--write-vasp-submit-markers", action=argparse.BooleanOptionalAction, default=True, help="Write .vasp_submit_* compatibility markers.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run prepared VASP folders inside an allocated compute node.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one prepared VASP directory.")
    run_parser.add_argument("job_dir", type=Path)
    add_run_options(run_parser)

    status_parser = subparsers.add_parser("status", help="Inspect one local-runner job directory.")
    status_parser.add_argument("job_dir", type=Path)

    ready_parser = subparsers.add_parser("mark-ready", help="Mark one prepared directory for local queue consumption.")
    ready_parser.add_argument("job_dir", type=Path)

    list_parser = subparsers.add_parser("list", help="List ready local-runner jobs under a queue root.")
    list_parser.add_argument("queue_dir", type=Path)
    list_parser.add_argument("--include-failed", action="store_true")

    watch_parser = subparsers.add_parser("watch", help="Run ready jobs under a queue root one at a time.")
    watch_parser.add_argument("queue_dir", type=Path)
    watch_parser.add_argument("--poll-seconds", type=float, default=30.0)
    watch_parser.add_argument("--once", action="store_true", help="Drain currently ready jobs once, then exit.")
    watch_parser.add_argument("--idle-exit-after", type=float, help="Exit after this many idle seconds.")
    watch_parser.add_argument("--max-jobs", type=int, help="Exit after running this many jobs.")
    watch_parser.add_argument("--include-failed", action="store_true")
    watch_parser.add_argument("--exit-on-failure", action="store_true")
    add_run_options(watch_parser)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        payload, code = run_job(args.job_dir, args)
        emit(payload)
        return code
    if args.command == "status":
        emit(status_job(args.job_dir))
        return 0
    if args.command == "mark-ready":
        payload = mark_ready(args.job_dir)
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "list":
        emit(list_jobs(args.queue_dir, args))
        return 0
    if args.command == "watch":
        payload, code = watch_jobs(args.queue_dir, args)
        emit(payload)
        return code

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
