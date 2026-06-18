"""Job index helpers: live SGE status plus recent-job listing and detail lookup.

Every prepared/submitted job writes a small JSON record under
`{root}/job_index/{job_uid}.json` (see ``renderer.write_job_metadata``). These
helpers read those records so the CLI can answer "what did I submit recently?"
and "show me job X" without re-running the whole prepare flow.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUMMARY_FIELDS = (
    "job_uid",
    "job_name",
    "task",
    "project",
    "state",
    "scheduler_id",
    "preset",
    "created_at",
    "submitted_at",
    "remote_dir",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def index_roots(config: dict[str, Any]) -> list[Path]:
    """`job_index` directories to scan, derived from trusted_roots + default root."""
    raw: list[str] = list(config.get("trusted_roots") or [])
    default_root = config.get("default_project_root")
    if default_root and default_root not in raw:
        raw.append(default_root)
    roots: list[Path] = []
    for item in raw:
        path = (Path(item).expanduser() / "job_index").resolve()
        if path not in roots:
            roots.append(path)
    return roots


def find_job_entry(job_uid: str, config: dict[str, Any]) -> dict[str, Any] | None:
    for index_dir in index_roots(config):
        path = index_dir / f"{job_uid}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            if isinstance(data, dict):
                data.setdefault("job_uid", job_uid)
                return data
    return None


def read_index_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index_dir in index_roots(config):
        if not index_dir.is_dir():
            continue
        for path in sorted(index_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            data.setdefault("job_uid", path.stem)
            data["_sort_key"] = (
                data.get("submitted_at")
                or data.get("created_at")
                or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            )
            entries.append(data)
    entries.sort(key=lambda item: item.get("_sort_key") or "", reverse=True)
    return entries


def summarize(entry: dict[str, Any]) -> dict[str, Any]:
    return {field: entry.get(field) for field in SUMMARY_FIELDS}


def list_jobs(config: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    entries = read_index_entries(config)
    jobs = [summarize(entry) for entry in entries[: max(limit, 0)]]
    return {"ok": True, "count": len(jobs), "total": len(entries), "jobs": jobs}


def resolve_status_target(
    identifier: str, config: dict[str, Any]
) -> tuple[str, str | None, str | None]:
    if identifier.isdigit():
        return identifier, None, None
    entry = find_job_entry(identifier, config)
    if entry is None:
        raise ValueError(f"Unknown job_uid: {identifier}")
    scheduler_id = entry.get("scheduler_id")
    if not scheduler_id:
        raise ValueError(f"job_uid {identifier} has no scheduler_id yet")
    return str(scheduler_id), entry.get("remote_dir"), identifier


def status_job(
    scheduler_id: str, remote_dir: str | None = None, job_uid: str | None = None
) -> dict[str, Any]:
    proc = subprocess.run(
        ["qstat", "-j", scheduler_id],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode == 0:
        return {
            "ok": True,
            "job_uid": job_uid,
            "scheduler_id": scheduler_id,
            "state": "running",
            "running": True,
            "finished": False,
            "stdout": proc.stdout.strip(),
        }

    result: dict[str, Any] = {
        "ok": True,
        "job_uid": job_uid,
        "scheduler_id": scheduler_id,
        "state": "unknown",
        "running": False,
        "finished": False,
        "qstat_stderr": proc.stderr.strip(),
    }
    if remote_dir:
        directory = Path(remote_dir).expanduser()
        finished_marker = directory / ".vasp_submit_finished"
        exit_code_path = directory / ".vasp_submit_exit_code"
        if finished_marker.exists():
            exit_code = (
                exit_code_path.read_text(encoding="utf-8").strip()
                if exit_code_path.exists()
                else None
            )
            result.update(
                {
                    "state": "finished" if exit_code == "0" else "failed",
                    "finished": True,
                    "exit_code": exit_code,
                    "finished_at": finished_marker.read_text(encoding="utf-8").strip(),
                }
            )
    return result


def show_job(identifier: str, config: dict[str, Any]) -> dict[str, Any]:
    """Full detail for one job: stored metadata + live SGE status.

    Works for a vasp-submit job_uid (prepared or submitted) or a raw SGE id.
    """
    if identifier.isdigit():
        status = status_job(identifier)
        return {"ok": True, "job_uid": None, "scheduler_id": identifier, "metadata": None, "status": status}

    entry = find_job_entry(identifier, config)
    if entry is None:
        raise ValueError(f"Unknown job_uid: {identifier}")
    metadata = {key: value for key, value in entry.items() if not key.startswith("_")}
    scheduler_id = entry.get("scheduler_id")
    if scheduler_id:
        status = status_job(str(scheduler_id), entry.get("remote_dir"), identifier)
    else:
        status = {
            "ok": True,
            "job_uid": identifier,
            "state": entry.get("state") or "prepared",
            "running": False,
            "finished": False,
            "note": "prepared but not submitted yet",
        }
    return {"ok": True, "job_uid": identifier, "metadata": metadata, "status": status}
