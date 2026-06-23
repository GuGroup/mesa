from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from vasp_submit.common.config import default_config_path, dump_yaml, load_yaml
from vasp_submit.common.schema import JOB_SPEC_SCHEMA
from vasp_submit.common.spec import load_and_resolve_spec, load_spec_text
from vasp_submit.hpc_server.jobs import list_jobs, resolve_status_target, show_job, status_job
from vasp_submit.hpc_server.renderer import prepare_job, submit_job


def read_spec_arg(value: str) -> tuple[dict[str, Any], str, Path]:
    if value == "-":
        text = sys.stdin.read()
        base_dir = Path.cwd()
    else:
        path = Path(value)
        text = path.read_text(encoding="utf-8")
        base_dir = path.resolve().parent
    return load_spec_text(text), text, base_dir


def prepared_result(directory: Path) -> dict[str, Any]:
    return {"ok": True, "prepared": True, "job_uid": directory.name, "remote_dir": str(directory)}


def json_print(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=True, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vasp-job")
    parser.add_argument("--config", type=Path, default=default_config_path("hpc-server"))
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_p = sub.add_parser("prepare", help="Write VASP input files without submitting")
    prepare_p.add_argument("input", help="JSON/YAML spec path, or '-' to read from stdin")
    prepare_p.add_argument("--common", type=Path, default=None, help="Reusable common spec file merged under this spec (this spec wins)")

    submit_p = sub.add_parser("submit", help="Write input files and submit with qsub")
    submit_p.add_argument("input", help="JSON/YAML spec path, or '-' to read from stdin")
    submit_p.add_argument("--common", type=Path, default=None, help="Reusable common spec file merged under this spec (this spec wins)")

    status_p = sub.add_parser("status", help="Live SGE status for one job")
    status_p.add_argument("identifier", help="SGE scheduler_id or vasp-submit job_uid")
    status_p.add_argument("remote_dir", nargs="?")

    list_p = sub.add_parser("list", help="Recent jobs with compact status fields")
    list_p.add_argument("--limit", type=int, default=20, help="Max jobs to show (default 20)")
    list_p.add_argument("--verbose", action="store_true", help="Include timestamps, preset, project, and remote_dir")

    show_p = sub.add_parser("show", help="Full metadata + live status for one job")
    show_p.add_argument("identifier", help="vasp-submit job_uid or SGE scheduler_id")

    sub.add_parser("schema", help="Print the accepted job spec JSON schema")

    args = parser.parse_args(argv)
    config = load_yaml(args.config)

    try:
        if args.command in {"prepare", "submit"}:
            spec, original, spec_base_dir = read_spec_arg(args.input)
            had_inheritance = ("extends" in spec) or (args.common is not None)
            spec = load_and_resolve_spec(spec, spec_base_dir, common_path=args.common)
            if had_inheritance:
                # Record the fully merged spec so the preserved input is
                # self-contained (the raw spec only had an `extends` pointer).
                original = dump_yaml(spec)
            directory = prepare_job(spec, config, original, spec_base_dir=spec_base_dir)
            if args.command == "prepare":
                json_print(prepared_result(directory))
            else:
                json_print(submit_job(directory))
        elif args.command == "status":
            scheduler_id, remote_dir, job_uid = resolve_status_target(args.identifier, config)
            json_print(status_job(scheduler_id, args.remote_dir or remote_dir, job_uid))
        elif args.command == "list":
            json_print(list_jobs(config, args.limit, verbose=args.verbose))
        elif args.command == "show":
            json_print(show_job(args.identifier, config))
        elif args.command == "schema":
            json_print(JOB_SPEC_SCHEMA)
    except Exception as exc:
        json_print({"ok": False, "error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
