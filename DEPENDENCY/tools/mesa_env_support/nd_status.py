"""Status and event-log helpers for initialize-mesa."""
from __future__ import annotations

from .common import *

def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def handoff_config(contracts: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(contracts, dict):
        return {}
    handoff = contracts.get("handoff", {})
    return handoff if isinstance(handoff, dict) else {}

def contract_output_names(contracts: dict[str, Any] | None = None) -> dict[str, str]:
    handoff = handoff_config(contracts)
    return {
        "status_markdown": str(handoff.get("status_markdown", "initialize_status.md")),
        "events_jsonl": str(handoff.get("events_jsonl", "initialize_events.jsonl")),
        "runtime_plan_dir": str(handoff.get("runtime_plan_dir", "runtime_plans")),
        "analyzer_json": str(handoff.get("analyzer_output_json", "nondeterministic_profile.json")),
        "analyzer_markdown": str(handoff.get("analyzer_output_markdown", "nondeterministic_profile.md")),
    }

def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "runtime"

def append_initialize_event(
    output_dir: Path | None,
    event: str,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
    contracts: dict[str, Any] | None = None,
) -> Path:
    names = contract_output_names(contracts)
    out_dir = initialization_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    event_path = out_dir / names["events_jsonl"]
    record: dict[str, Any] = {
        "timestamp": utc_timestamp(),
        "event": event,
        "status": status,
        "message": message,
    }
    if details:
        record["details"] = details
    with event_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return event_path

def read_recent_events(output_dir: Path | None, limit: int = 20, contracts: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    names = contract_output_names(contracts)
    out_dir = initialization_dir(output_dir)
    event_path = out_dir / names["events_jsonl"]
    if not event_path.is_file():
        return []
    lines = event_path.read_text(encoding="utf-8").splitlines()[-limit:]
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            event = json.loads(line)
        except Exception:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events

def status_artifact_state(output_dir: Path | None, contracts: dict[str, Any] | None = None) -> dict[str, Any]:
    names = contract_output_names(contracts)
    out_dir = initialization_dir(output_dir)
    plan_dir = out_dir / names["runtime_plan_dir"]
    plan_jsons = sorted(plan_dir.glob("*_plan.json")) if plan_dir.is_dir() else []
    return {
        "output_dir": str(out_dir),
        "nondeterministic_profile_json": str(out_dir / names["analyzer_json"]),
        "nondeterministic_profile_json_exists": (out_dir / names["analyzer_json"]).is_file(),
        "nondeterministic_profile_md": str(out_dir / names["analyzer_markdown"]),
        "nondeterministic_profile_md_exists": (out_dir / names["analyzer_markdown"]).is_file(),
        "runtime_plan_dir": str(plan_dir),
        "runtime_plan_count": len(plan_jsons),
        "runtime_plans": [str(path) for path in plan_jsons],
        "events_jsonl": str(out_dir / names["events_jsonl"]),
        "events_jsonl_exists": (out_dir / names["events_jsonl"]).is_file(),
    }

def render_initialize_status(
    output_dir: Path | None,
    events: list[dict[str, Any]],
    contracts: dict[str, Any] | None = None,
    headline: str | None = None,
) -> str:
    state = status_artifact_state(output_dir, contracts)
    out_dir = Path(state["output_dir"])
    out_dir_arg = shlex.quote(display_path(out_dir))
    lines = [
        "# MESA Initialize Status",
        "",
        headline or "Initialization status for this repository.",
        "",
        "## Artifacts",
        "",
        f"- Output directory: `{out_dir}`",
        f"- Non-deterministic profile JSON: `{'OK' if state['nondeterministic_profile_json_exists'] else 'MISSING'}` {state['nondeterministic_profile_json']}",
        f"- Non-deterministic profile Markdown: `{'OK' if state['nondeterministic_profile_md_exists'] else 'MISSING'}` {state['nondeterministic_profile_md']}",
        f"- Runtime plan directory: `{state['runtime_plan_dir']}`",
        f"- Runtime plans: `{state['runtime_plan_count']}`",
        f"- Event log: `{'OK' if state['events_jsonl_exists'] else 'MISSING'}` {state['events_jsonl']}",
        "",
        "## Recent Events",
        "",
    ]
    if not events:
        lines.append("- No events recorded yet.")
    else:
        for event in events[-20:]:
            timestamp = event.get("timestamp", "unknown-time")
            status = event.get("status", "unknown")
            name = event.get("event", "event")
            message = event.get("message", "")
            lines.append(f"- `{timestamp}` `{status}` `{name}` {message}")

    lines.extend(
        [
            "",
            "## Safe Next Commands",
            "",
            "- Analyze machine-specific facts:",
            f"  `uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py analyze-nondeterministic --output-dir {out_dir_arg}`",
            "- Generate a non-deterministic runtime plan:",
            f"  `uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py generate-runtime-plan mesa-uma --project-dir {out_dir_arg}`",
            "- Dry-run a saved runtime plan:",
            f"  `uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan {display_path(Path(state['runtime_plan_dir']) / 'mesa-uma_plan.json')} --project-dir {out_dir_arg}`",
            "- Execute a saved runtime plan only after reviewing it:",
            f"  `uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan {display_path(Path(state['runtime_plan_dir']) / 'mesa-uma_plan.json')} --project-dir {out_dir_arg} --yes`",
            "",
        ]
    )
    return "\n".join(lines)

def write_initialize_status(
    output_dir: Path | None,
    contracts: dict[str, Any] | None = None,
    headline: str | None = None,
) -> Path:
    names = contract_output_names(contracts)
    out_dir = initialization_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    events = read_recent_events(out_dir, contracts=contracts)
    status_path = out_dir / names["status_markdown"]
    status_path.write_text(render_initialize_status(out_dir, events, contracts, headline), encoding="utf-8")
    return status_path
