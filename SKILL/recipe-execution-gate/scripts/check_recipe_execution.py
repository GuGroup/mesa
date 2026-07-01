#!/usr/bin/env python3
"""Validate recipe-local execution manifests and shared artifact links."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REQUIRED_MANIFEST_FIELDS = [
    "source_recipe",
    "source_procedure_id",
    "skill_or_script_used",
    "command",
    "input_artifacts",
    "output_artifacts",
    "validation_status",
    "acceptance_state",
    "caveats",
]
ALLOWED_ACCEPTANCE = {"accepted", "accepted-with-caveat", "exploratory", "failed", "excluded"}


def main() -> int:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve() if args.project_root else Path.cwd().resolve()
    recipe_root = args.recipe_root.expanduser().resolve()
    outdir = args.outdir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    shared_roots = auto_shared_roots(recipe_root) + [
        resolve_path(path, project_root, project_root).resolve()
        for path in args.shared_root
    ]
    shared_roots = unique_paths([path for path in shared_roots if path.exists()])

    calc_dirs = discover_calculation_dirs(recipe_root)
    records: list[dict[str, Any]] = []
    path_issues: list[dict[str, Any]] = []
    declared_outputs: set[Path] = set()

    for calc_dir in calc_dirs:
        record, issues, outputs = check_calculation(calc_dir, recipe_root, project_root, shared_roots)
        records.append(record)
        path_issues.extend(issues)
        declared_outputs.update(outputs)

    if args.check_shared_orphans:
        path_issues.extend(find_shared_orphans(shared_roots, declared_outputs, project_root))

    error_count = sum(1 for issue in path_issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in path_issues if issue["severity"] == "warning")
    status = "fail" if error_count else ("pass-with-warnings" if warning_count else "pass")

    report = {
        "schema_version": 1,
        "status": status,
        "recipe_root": rel(recipe_root, project_root),
        "project_root": str(project_root),
        "shared_roots": [rel(path, project_root) for path in shared_roots],
        "calculation_count": len(records),
        "manifest_count": sum(1 for record in records if record["manifest_exists"]),
        "error_count": error_count,
        "warning_count": warning_count,
        "local_output_count": sum(record["local_output_count"] for record in records),
        "shared_output_count": sum(record["shared_output_count"] for record in records),
        "external_output_count": sum(record["external_output_count"] for record in records),
        "records": records,
        "path_issues": path_issues,
    }

    write_json(outdir / "recipe_execution_gate_report.json", report)
    write_records_csv(outdir / "manifest_index.csv", records)
    write_issues_csv(outdir / "path_issues.csv", path_issues)
    write_markdown(outdir / "recipe_execution_gate_report.md", report)

    print(json.dumps({
        "status": status,
        "calculation_count": len(records),
        "error_count": error_count,
        "warning_count": warning_count,
        "outputs": rel(outdir, project_root),
    }, indent=2))
    return 2 if error_count else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate MESA recipe execution manifests and shared artifact links.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--recipe-root", required=True, type=Path, help="Path to S*_explicit_recipe directory.")
    parser.add_argument("--project-root", type=Path, default=None, help="Root used to resolve relative artifact paths.")
    parser.add_argument("--outdir", required=True, type=Path, help="Directory for gate reports.")
    parser.add_argument("--shared-root", action="append", default=[], type=Path, help="Additional allowed shared output root.")
    parser.add_argument("--check-shared-orphans", action="store_true", help="Also scan allowed shared roots for files not linked by any manifest.")
    return parser.parse_args()


def discover_calculation_dirs(recipe_root: Path) -> list[Path]:
    out: list[Path] = []
    for calc_parent in sorted(recipe_root.glob("P*/calculations")):
        if not calc_parent.is_dir():
            continue
        out.extend(sorted(path for path in calc_parent.iterdir() if path.is_dir() and path.name.startswith("C")))
    return out


def check_calculation(
    calc_dir: Path,
    recipe_root: Path,
    project_root: Path,
    shared_roots: list[Path],
) -> tuple[dict[str, Any], list[dict[str, Any]], set[Path]]:
    recipe_path = calc_dir / "recipe.json"
    execution_dir = calc_dir / "execution"
    manifest_path = execution_dir / "execution_manifest.json"
    issues: list[dict[str, Any]] = []
    declared_outputs: set[Path] = set()

    recipe = read_json(recipe_path)
    manifest = read_json(manifest_path)
    record: dict[str, Any] = {
        "calculation_dir": rel(calc_dir, project_root),
        "recipe_path": rel(recipe_path, project_root),
        "execution_dir": rel(execution_dir, project_root),
        "manifest_path": rel(manifest_path, project_root),
        "recipe_exists": recipe_path.exists(),
        "execution_dir_exists": execution_dir.exists(),
        "manifest_exists": manifest_path.exists(),
        "source_recipe_ok": False,
        "procedure_id_ok": False,
        "acceptance_state": None,
        "validation_status": None,
        "local_output_count": 0,
        "shared_output_count": 0,
        "external_output_count": 0,
        "missing_output_count": 0,
        "missing_input_count": 0,
        "issue_count": 0,
    }

    if not recipe_path.exists():
        issues.append(issue("error", calc_dir, "missing_recipe", recipe_path, "recipe.json is missing", project_root))
    if not execution_dir.exists():
        issues.append(issue("error", calc_dir, "missing_execution_dir", execution_dir, "execution/ directory is missing", project_root))
    if not manifest_path.exists():
        issues.append(issue("error", calc_dir, "missing_manifest", manifest_path, "execution_manifest.json is missing", project_root))
        record["issue_count"] = len(issues)
        return record, issues, declared_outputs
    if manifest is None:
        issues.append(issue("error", calc_dir, "invalid_manifest_json", manifest_path, "execution_manifest.json is not valid JSON", project_root))
        record["issue_count"] = len(issues)
        return record, issues, declared_outputs

    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            issues.append(issue("error", calc_dir, "missing_manifest_field", manifest_path, f"missing field: {field}", project_root))

    source_recipe = resolve_path(manifest.get("source_recipe"), project_root, calc_dir)
    if source_recipe and source_recipe.exists() and source_recipe.resolve() == recipe_path.resolve():
        record["source_recipe_ok"] = True
    else:
        issues.append(issue("error", calc_dir, "source_recipe_mismatch", source_recipe or manifest_path, "source_recipe does not resolve to local recipe.json", project_root))

    recipe_procedure = recipe.get("procedure_id") if isinstance(recipe, dict) else None
    if recipe_procedure and manifest.get("source_procedure_id") == recipe_procedure:
        record["procedure_id_ok"] = True
    else:
        issues.append(issue("error", calc_dir, "procedure_id_mismatch", manifest_path, "source_procedure_id does not match recipe procedure_id", project_root))

    acceptance = manifest.get("acceptance_state")
    validation = manifest.get("validation_status")
    record["acceptance_state"] = acceptance
    record["validation_status"] = validation
    if acceptance not in ALLOWED_ACCEPTANCE:
        issues.append(issue("error", calc_dir, "invalid_acceptance_state", manifest_path, f"invalid acceptance_state: {acceptance!r}", project_root))
    if not manifest.get("command"):
        issues.append(issue("warning", calc_dir, "empty_command", manifest_path, "command is empty or missing", project_root))
    if acceptance in {"accepted-with-caveat", "failed", "excluded"} and not manifest.get("caveats"):
        issues.append(issue("warning", calc_dir, "missing_caveats", manifest_path, f"{acceptance} should include caveats", project_root))

    for input_value in ensure_list(manifest.get("input_artifacts")):
        input_path = resolve_path(input_value, project_root, execution_dir)
        if input_path is None or not input_path.exists():
            record["missing_input_count"] += 1
            issues.append(issue("error", calc_dir, "missing_input_artifact", input_path or manifest_path, f"listed input artifact missing: {input_value}", project_root))

    for output_value in ensure_list(manifest.get("output_artifacts")):
        output_path = resolve_path(output_value, project_root, execution_dir)
        if output_path is None:
            record["missing_output_count"] += 1
            issues.append(issue("error", calc_dir, "invalid_output_artifact", manifest_path, f"invalid output artifact path: {output_value}", project_root))
            continue
        output_resolved = output_path.resolve()
        declared_outputs.add(output_resolved)
        if not output_path.exists():
            record["missing_output_count"] += 1
            issues.append(issue("error", calc_dir, "missing_output_artifact", output_path, f"listed output artifact missing: {output_value}", project_root))
        if is_relative_to(output_resolved, execution_dir.resolve()):
            record["local_output_count"] += 1
        elif any(is_relative_to(output_resolved, shared_root.resolve()) for shared_root in shared_roots):
            record["shared_output_count"] += 1
        else:
            record["external_output_count"] += 1
            issues.append(issue("error", calc_dir, "external_output_artifact", output_path, "output is outside local execution/ and allowed shared roots", project_root))

    if execution_dir.exists():
        for path in sorted(p for p in execution_dir.rglob("*") if p.is_file()):
            if path.resolve() == manifest_path.resolve():
                continue
            if path.resolve() not in declared_outputs:
                issues.append(issue("warning", calc_dir, "orphan_local_execution_file", path, "local execution file is not listed in output_artifacts", project_root))

    record["issue_count"] = len(issues)
    return record, issues, declared_outputs


def auto_shared_roots(recipe_root: Path) -> list[Path]:
    name = recipe_root.name
    if not name.endswith("_explicit_recipe"):
        return []
    strategy_id = name[: -len("_explicit_recipe")]
    parent = recipe_root.parent
    return [
        parent / f"{strategy_id}_execution",
        parent / f"{strategy_id}_shared_execution",
    ]


def find_shared_orphans(shared_roots: list[Path], declared_outputs: set[Path], project_root: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for root in shared_roots:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if path.resolve() not in declared_outputs:
                issues.append({
                    "severity": "warning",
                    "calculation_dir": None,
                    "code": "orphan_shared_file",
                    "path": rel(path, project_root),
                    "message": "shared file is not listed by any recipe-local manifest",
                })
    return issues


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_path(value: Any, project_root: Path, base_dir: Path) -> Path | None:
    if value is None or value == "":
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    root_candidate = project_root / path
    if root_candidate.exists() or str(value).startswith(("project/", "SKILL/", "ENVIRONMENT/")):
        return root_candidate
    return base_dir / path


def issue(severity: str, calc_dir: Path, code: str, path: Path, message: str, project_root: Path) -> dict[str, Any]:
    return {
        "severity": severity,
        "calculation_dir": rel(calc_dir, project_root),
        "code": code,
        "path": rel(path, project_root),
        "message": message,
    }


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def unique_paths(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            out.append(resolved)
            seen.add(resolved)
    return out


def rel(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except Exception:
        return str(path)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_records_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "calculation_dir",
        "recipe_exists",
        "execution_dir_exists",
        "manifest_exists",
        "source_recipe_ok",
        "procedure_id_ok",
        "acceptance_state",
        "validation_status",
        "local_output_count",
        "shared_output_count",
        "external_output_count",
        "missing_output_count",
        "missing_input_count",
        "issue_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def write_issues_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["severity", "calculation_dir", "code", "path", "message"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Recipe Execution Gate Report",
        "",
        f"Status: `{report['status']}`",
        f"Recipe root: `{report['recipe_root']}`",
        f"Calculation folders: {report['calculation_count']}",
        f"Execution manifests: {report['manifest_count']}",
        f"Errors: {report['error_count']}",
        f"Warnings: {report['warning_count']}",
        f"Local linked outputs: {report['local_output_count']}",
        f"Shared linked outputs: {report['shared_output_count']}",
        f"External linked outputs: {report['external_output_count']}",
        "",
        "Allowed shared roots:",
    ]
    if report["shared_roots"]:
        lines.extend(f"- `{root}`" for root in report["shared_roots"])
    else:
        lines.append("- none")
    lines.append("")
    issues = report["path_issues"]
    if not issues:
        lines.append("No path or manifest issues were found.")
    else:
        lines.append("## Issues")
        lines.append("")
        for item in issues[:200]:
            lines.append(
                f"- `{item['severity']}` `{item['code']}` in "
                f"`{item.get('calculation_dir')}`: {item['message']} "
                f"(`{item.get('path')}`)"
            )
        if len(issues) > 200:
            lines.append(f"- ... {len(issues) - 200} additional issues omitted from Markdown; see JSON/CSV.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
