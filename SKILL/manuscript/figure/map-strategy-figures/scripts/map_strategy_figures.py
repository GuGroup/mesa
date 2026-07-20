#!/usr/bin/env python3
"""Map generic figure intents to recipe evidence without judging results."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.5"
VALID_LEVELS = {"must_have", "useful", "supplementary"}
MISSING_NAMES = ("missing_evidence_summary.json", "missing_evidence_records.json")
MISSING_STATES = {"blocked", "excluded", "unresolved"}
STRUCTURE_EXTS = {".vasp", ".cif", ".xyz", ".extxyz", ".traj", ".poscar", ".contcar"}
EXT_PRIORITY = {".png": 0, ".svg": 1, ".pdf": 2, ".json": 3, ".csv": 4, ".md": 5}


FIGURE_INTENT_PROMPT = """You are an expert in computational chemistry for heterogeneous catalysis.
Identify conventional figure types directly supported by the supplied computational workflow.

The input contains only models, methods, adsorption_sites, and procedures.

Rules:
1. Do not infer calculations that are not explicitly described.
2. Do not recommend experimental characterization or performance plots.
3. Do not recommend unsupported descriptors.
4. Use generic, academically conventional figure names.
5. Assign exactly one level: must_have, useful, or supplementary.

Return JSON only:
{
  "figures": [
    {"figure_type": "<generic figure name>", "level": "must_have | useful | supplementary"}
  ]
}
"""


FIGURE_ROUTES = (
    {
        "type": "structure-grid",
        "skill": "render-adsorbate-structure-grid",
        "keywords": ("optimized adsorption configuration", "adsorbate configuration", "adsorbate structures"),
        "roles": ("adsorbate_relaxation_matrix",),
        "text": ("relax", "adsorbate", "adsorption", "configuration", "optimized"),
        "artifacts": ("relax", ".traj", ".extxyz", "poscar", "contcar", ".vasp"),
    },
    {
        "type": "structure-grid",
        "skill": "render-adsorbate-structure-grid",
        "keywords": ("computational model", "model structure", "structure", "slab", "active site", "adsorption site"),
        "roles": ("structure_model_build",),
        "text": ("build", "model", "structure", "slab", "site", "motif"),
        "artifacts": ("poscar", "contcar", ".vasp", ".cif", ".xyz", ".traj", "model_metadata"),
    },
    {
        "type": "energy-diagram",
        "skill": "plot-energy-diagram",
        "keywords": ("free-energy diagram", "free energy diagram", "reaction energy profile", "energy profile", "reaction coordinate"),
        "roles": ("free_energy_diagram_assembly", "electrochemical_free_energy_bookkeeping", "potential_shift_analysis"),
        "text": ("free-energy diagram", "free energy diagram", "relative free energies", "reaction coordinate", "potential"),
        "artifacts": ("energy_diagram", "free_energy", "relative_free_energies", "plot", "state_table"),
    },
    {
        "type": "descriptor-comparison",
        "skill": "create-nature-figure",
        "keywords": ("adsorption free-energy comparison", "free-energy comparison", "descriptor comparison", "thermodynamic descriptor", "limiting-step comparison"),
        "roles": ("descriptor_calculation",),
        "text": ("delta g", "deltag", "adsorption energy", "descriptor", "thermodynamic", "largest uphill"),
        "artifacts": ("delta_g", "adsorption", "descriptor", "thermodynamic", "largest_uphill"),
    },
    {
        "type": "electronic-descriptor",
        "skill": "create-nature-figure",
        "keywords": ("projected density of states", "density of states", "projected dos", "pdos"),
        "roles": ("density_of_states_analysis", "projected_dos_analysis"),
        "text": ("projected dos", "density of states", "pdos"),
        "artifacts": ("dos", "pdos", "projected"),
    },
    {
        "type": "electronic-descriptor",
        "skill": "create-nature-figure",
        "keywords": ("charge density difference", "charge transfer", "bader charge", "charge analysis"),
        "roles": ("charge_transfer_analysis",),
        "text": ("charge density", "charge transfer", "bader", "charge analysis"),
        "artifacts": ("charge", "bader", "density"),
    },
    {
        "type": "calculation-diagnostic",
        "skill": "analyze-calculation-results",
        "keywords": ("local geometry analysis", "geometry analysis", "bond length", "coordination", "relaxation", "relaxed structure"),
        "roles": ("clean_structure_relaxation", "adsorbate_relaxation_matrix", "geometry_optimization"),
        "text": ("relax", "geometry", "bond", "coordination", "distance"),
        "artifacts": ("analysis_summary", "metrics", "relax", "geometry", ".traj", ".extxyz"),
    },
)


def read_json_or_python(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        tree = ast.parse(text, filename=str(path))
        preferred = {"selected_strategy", "generated_strategies", "strategies", "result", "data"}
        fallback: list[ast.AST] = []
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if preferred.intersection(names):
                return ast.literal_eval(node.value)
            fallback.append(node.value)
        if fallback:
            return ast.literal_eval(fallback[0])
    raise ValueError(f"Could not load JSON or Python literal from {path}")


def unique(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    output: list[Any] = []
    for value in values:
        key = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value is None else [value])


def words(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(words(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(words(item) for item in value)
    return "" if value is None else str(value)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "figure"


def select_strategy(payload: Any, strategy_id: str | None) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("selected_strategy"), dict):
        return payload["selected_strategy"]
    if isinstance(payload, dict) and payload.get("strategy_id"):
        return payload
    candidates: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        for key in ("strategies", "generated_strategies", "items"):
            candidates.extend(item for item in as_list(payload.get(key)) if isinstance(item, dict))
    elif isinstance(payload, list):
        candidates = [item for item in payload if isinstance(item, dict)]
    if strategy_id:
        for candidate in candidates:
            if candidate.get("strategy_id") == strategy_id:
                return candidate
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError("Could not determine selected strategy; pass --strategy-id")


def computational(strategy: dict[str, Any]) -> dict[str, Any]:
    for key in ("experiment", "experimental"):
        block = strategy.get(key)
        if isinstance(block, dict) and isinstance(block.get("computational"), dict):
            return block["computational"]
    return strategy.get("computational") if isinstance(strategy.get("computational"), dict) else strategy


def strategy_input(strategy: dict[str, Any]) -> dict[str, Any]:
    block = computational(strategy)
    dft = block.get("dft_details") if isinstance(block.get("dft_details"), dict) else {}
    fallback_dft = strategy.get("dft_details") if isinstance(strategy.get("dft_details"), dict) else {}
    return {
        "models": as_list(block.get("models") or strategy.get("models")),
        "methods": as_list(block.get("methods") or strategy.get("methods")),
        "adsorption_sites": as_list(dft.get("adsorption_sites") or fallback_dft.get("adsorption_sites")),
        "procedures": as_list(block.get("procedures") or strategy.get("procedures")),
    }


def strategy_claim(strategy: dict[str, Any]) -> str:
    for path in (("hypothesis", "statement"), ("conclusion", "statement"), ("problem", "question"), ("title",)):
        value: Any = strategy
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:360]
    return ""


def normalize_level(value: Any) -> str:
    value = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return {
        "musthave": "must_have", "required": "must_have", "essential": "must_have", "main": "must_have",
        "supporting": "useful", "optional": "useful", "si": "supplementary",
        "supporting_information": "supplementary",
    }.get(value, value)


def parse_json_text(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = json.loads(text[text.find("{") : text.rfind("}") + 1])
    if not isinstance(payload, dict):
        raise ValueError("Figure intent output must be a JSON object")
    return payload


def normalize_intents(payload: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(payload.get("figures"), list):
        raise ValueError("Figure intent JSON must contain a figures list")
    intents: list[dict[str, str]] = []
    for item in payload["figures"]:
        if not isinstance(item, dict):
            continue
        figure_type = " ".join(str(item.get("figure_type", "")).split())
        level = normalize_level(item.get("level"))
        if figure_type and level in VALID_LEVELS:
            intents.append({"figure_type": figure_type, "level": level})
    return unique(intents)


def output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    chunks: list[str] = []
    for item in as_list(response.get("output")):
        for content in as_list(item.get("content") if isinstance(item, dict) else None):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def load_env() -> None:
    for path in (Path.cwd() / ".env", Path.cwd() / "DEPENDENCY/.env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def request_intents(model: str, prompt: str, api_key: str) -> dict[str, Any]:
    body = json.dumps({"model": model, "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]}).encode()
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"OpenAI API HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"OpenAI API request failed: {exc.reason}") from exc


def recipe_entries(recipe_root: Path, index: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for procedure in index.get("procedures", []):
        if not isinstance(procedure, dict):
            continue
        for calculation in procedure.get("calculations", []):
            if not isinstance(calculation, dict):
                continue
            pid, cid = str(procedure.get("procedure_id", "")), str(calculation.get("calculation_id", ""))
            calc_dir = recipe_root / str(calculation.get("folder", ""))
            manifest_path = calc_dir / "execution/execution_manifest.json"
            manifest = read_json_or_python(manifest_path) if manifest_path.exists() else {}
            entries.append({
                "procedure_id": pid,
                "calculation_ref": f"{pid}/{cid}" if pid and cid else cid or pid,
                "procedure_text": str(procedure.get("source_text", "")),
                "calculation_title": str(calculation.get("calculation_title", "")),
                "recipe_role": str(calculation.get("recipe_role", "")),
                "calc_dir": calc_dir,
                "manifest": manifest if isinstance(manifest, dict) else {},
            })
    return entries


def entry_artifacts(entry: dict[str, Any]) -> list[str]:
    manifest = entry["manifest"]
    return unique([
        str(value)
        for key in ("output_artifacts", "input_artifacts")
        for value in as_list(manifest.get(key))
    ])


def missing_files(entry: dict[str, Any]) -> list[Path]:
    execution = entry["calc_dir"] / "execution"
    paths = [execution / name for name in MISSING_NAMES]
    if execution.exists():
        for folder in execution.glob("missing_evidence*"):
            if folder.is_dir():
                paths.extend(folder / name for name in MISSING_NAMES)
    for artifact in entry_artifacts(entry):
        if Path(artifact).name in MISSING_NAMES:
            paths.append(Path(artifact))
    return unique([path for path in paths if path.exists()])


def raised_missing_evidence(entry: dict[str, Any]) -> list[dict[str, Any]]:
    by_folder: dict[Path, dict[str, Any]] = {}
    for path in missing_files(entry):
        payload = read_json_or_python(path)
        if not isinstance(payload, dict):
            continue
        records = payload.get("records") if isinstance(payload.get("records"), list) else []
        state = str(payload.get("status", "")).lower()
        raised = state in MISSING_STATES or bool(records) or int(payload.get("record_count") or 0) > 0
        if not raised:
            continue
        reasons = unique([str(payload.get("reason", ""))] + [str(record.get("reason", "")) for record in records if isinstance(record, dict)])
        missing = unique([
            str(record.get("missing_artifacts", ""))
            for record in records
            if isinstance(record, dict) and record.get("missing_artifacts")
        ])
        record = {
            "calculation": entry["calculation_ref"],
            "source": str(path),
            "reason": next((reason for reason in reasons if reason), "Required evidence is missing."),
            "missing_artifacts": missing,
            "record_count": int(payload.get("record_count") or len(records)),
        }
        previous = by_folder.get(path.parent)
        if previous is None or path.name == "missing_evidence_summary.json":
            by_folder[path.parent] = record
    return list(by_folder.values())


def route_for(name: str) -> dict[str, Any]:
    lower = name.lower()
    for route in FIGURE_ROUTES:
        if any(keyword in lower for keyword in route["keywords"]):
            return route
    fallback = tuple(token for token in re.split(r"[^a-z0-9]+", lower) if len(token) > 3)
    return {"type": slug(name), "skill": "", "keywords": fallback, "roles": (), "text": fallback, "artifacts": fallback}


def matches(entry: dict[str, Any], route: dict[str, Any]) -> bool:
    roles = {role.lower() for role in route["roles"]}
    if roles:
        return entry["recipe_role"].lower() in roles
    text = words([entry["procedure_text"], entry["calculation_title"]]).lower()
    artifacts = words([Path(path).name for path in entry_artifacts(entry)]).lower()
    return any(term in text for term in route["text"]) or any(term in artifacts for term in route["artifacts"])


def route_artifacts(route: dict[str, Any], entries: list[dict[str, Any]], limit: int) -> list[str]:
    artifacts = unique([artifact for entry in entries for artifact in entry_artifacts(entry)])
    terms = route["artifacts"]
    selected = [path for path in artifacts if any(term in Path(path).name.lower() for term in terms)] or artifacts
    def sort_key(path: str) -> tuple[int, int, str]:
        suffix = Path(path.lower()).suffix
        structure = Path(path.lower()).name in {"poscar", "contcar"} or suffix in STRUCTURE_EXTS
        return (-1 if structure else EXT_PRIORITY.get(suffix, 9), len(path), path)
    return sorted(selected, key=sort_key)[:limit]


def quantities(route: dict[str, Any], entries: list[dict[str, Any]]) -> list[str]:
    text = words([entry["procedure_text"] for entry in entries]).lower()
    found: list[str] = []
    if "free energy" in text or "free-energy" in text:
        found.append("free_energy_profile" if "diagram" in text or "profile" in text else "free_energy")
    if "density of states" in text or "pdos" in text:
        found.append("projected_dos")
    if "charge density difference" in text:
        found.append("charge_density_difference")
    if "descriptor" in text or "largest uphill" in text or "maximum uphill" in text:
        found.append("descriptor_comparison")
    return found or [route["type"]]


def build_mapping(strategy: dict[str, Any], index: dict[str, Any], recipe_root: Path, intents: list[dict[str, str]], artifact_limit: int) -> dict[str, Any]:
    entries = recipe_entries(recipe_root, index)
    figures: list[dict[str, Any]] = []
    all_blockers: list[dict[str, str]] = []
    for number, intent in enumerate(intents, start=1):
        route = route_for(intent["figure_type"])
        matched = [entry for entry in entries if matches(entry, route)]
        missing = unique([record for entry in matched for record in raised_missing_evidence(entry)])
        blockers = [f"{record['calculation']}: {record['reason']}" for record in missing]
        notes = [] if matched else ["No recipe entry matched this figure intent; retained without blocking."]
        figure = {
            "id": f"F{number}",
            "level": intent["level"],
            "figure_type": intent["figure_type"],
            "type": route["type"],
            "title": intent["figure_type"],
            "claim": strategy_claim(strategy),
            "source": {
                "procedures": sorted({entry["procedure_id"] for entry in matched if entry["procedure_id"]}),
                "calculations": sorted({entry["calculation_ref"] for entry in matched if entry["calculation_ref"]}),
            },
            "artifacts": route_artifacts(route, matched, artifact_limit),
            "status": "blocked" if missing else "mapped",
            "skill": route["skill"],
            "grounding": {
                "matched": bool(matched),
                "quantities": quantities(route, matched),
                "basis": unique([f"{entry['procedure_id']}: {' '.join(entry['procedure_text'].split())[:280]}" for entry in matched])[:3],
            },
            "caveats": unique([str(item) for entry in matched for item in as_list(entry["manifest"].get("caveats"))])[:8],
            "missing_evidence": missing,
            "blockers": blockers,
            "notes": notes,
        }
        figures.append(figure)
        all_blockers.extend({"figure": figure["id"], "reason": reason} for reason in blockers)
    return {
        "schema_version": 3,
        "mapper_mode": "llm_figure_intent",
        "strategy_id": str(strategy.get("strategy_id") or index.get("strategy_id") or ""),
        "figures": figures,
        "text_only_evidence": [],
        "blockers": all_blockers,
    }


def render_markdown(mapping: dict[str, Any]) -> str:
    lines = [
        f"# Figure Mapping for {mapping.get('strategy_id') or 'strategy'}", "",
        "| ID | Level | Figure Type | Routed Type | Status | Source |", "| --- | --- | --- | --- | --- | --- |",
    ]
    for figure in mapping["figures"]:
        source = ", ".join(figure["source"]["procedures"])
        lines.append(f"| {figure['id']} | {figure['level']} | {figure['figure_type']} | {figure['type']} | {figure['status']} | {source} |")
    for figure in mapping["figures"]:
        lines.extend(["", f"## {figure['id']} — {figure['figure_type']}"])
        lines.append(f"- Matched recipe evidence: `{figure['grounding']['matched']}`")
        lines.append(f"- Renderer: `{figure['skill'] or 'unregistered'}`")
        if figure["notes"]:
            lines.extend(f"- Note: {note}" for note in figure["notes"])
        if figure["missing_evidence"]:
            lines.append("- Missing evidence:")
            lines.extend(f"  - `{item['calculation']}`: {item['reason']}" for item in figure["missing_evidence"])
        if figure["caveats"]:
            lines.append("- Upstream caveats:")
            lines.extend(f"  - {item}" for item in figure["caveats"])
    return "\n".join(lines).rstrip() + "\n"


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Map generic strategy figure intents to recipe evidence.")
    cli.add_argument("--strategy", required=True)
    cli.add_argument("--recipe-root", required=True)
    cli.add_argument("--strategy-id")
    cli.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))
    cli.add_argument("--intent-json", help="Use saved intent JSON or an OpenAI response instead of calling the API.")
    cli.add_argument("--save-response")
    cli.add_argument("--save-prompt")
    cli.add_argument("--dry-run", action="store_true")
    cli.add_argument("--outdir")
    cli.add_argument("--figure-root")
    cli.add_argument("--artifact-limit", type=int, default=12)
    return cli


def main() -> int:
    load_env()
    args = parser().parse_args()
    recipe_root = Path(args.recipe_root)
    index_path = recipe_root / "recipe_index.json"
    if not index_path.exists():
        raise SystemExit(f"Missing recipe_index.json: {index_path}")
    index = read_json_or_python(index_path)
    strategy_id = args.strategy_id or (index.get("strategy_id") if isinstance(index, dict) else None)
    strategy = select_strategy(read_json_or_python(Path(args.strategy)), strategy_id)
    prompt = f"{FIGURE_INTENT_PROMPT}\nComputational workflow input:\n{json.dumps(strategy_input(strategy), indent=2)}\n"
    if args.save_prompt:
        Path(args.save_prompt).write_text(prompt, encoding="utf-8")
    if args.dry_run:
        print(json.dumps({"model": args.model, "strategy_id": strategy_id, "strategy_input": strategy_input(strategy), "prompt": prompt}, indent=2))
        return 0
    if args.intent_json:
        saved = read_json_or_python(Path(args.intent_json))
        intent_payload = saved if isinstance(saved, dict) and "figures" in saved else parse_json_text(output_text(saved))
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY is not set. Export it or provide --intent-json.")
        response = request_intents(args.model, prompt, api_key)
        if args.save_response:
            Path(args.save_response).write_text(json.dumps(response, indent=2), encoding="utf-8")
        intent_payload = parse_json_text(output_text(response))
    intents = normalize_intents(intent_payload)
    if not intents:
        raise SystemExit("No supported figure intents were returned.")
    mapping = build_mapping(strategy, index, recipe_root, intents, args.artifact_limit)
    if args.outdir and args.figure_root:
        raise SystemExit("Use either --outdir or --figure-root, not both.")
    outdir = Path(args.outdir) if args.outdir else Path(args.figure_root) / "mapping" if args.figure_root else recipe_root.parent / f"{mapping['strategy_id']}_figure/mapping"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "figure_info.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    (outdir / "figure_info.md").write_text(render_markdown(mapping), encoding="utf-8")
    print(f"Wrote {outdir / 'figure_info.json'}")
    print(f"Wrote {outdir / 'figure_info.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
