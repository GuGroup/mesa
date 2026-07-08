#!/usr/bin/env python3
"""Ask an LLM for strategy-backed figure intents, then attach local evidence."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.5"
GOOD_STATUSES = {"accepted", "accepted-with-caveat", "exploratory"}
BAD_STATUSES = {"failed", "excluded", "unsupported", "missing"}
STATUS_ORDER = {
    "accepted": 0,
    "accepted-with-caveat": 1,
    "exploratory": 2,
    "missing": 3,
    "unsupported": 4,
    "failed": 5,
    "excluded": 6,
}
EXT_PRIORITY = {".svg": 0, ".pdf": 1, ".png": 2, ".json": 3, ".csv": 4, ".md": 5}
STRUCTURE_EXTS = {".vasp", ".cif", ".xyz", ".extxyz", ".traj", ".poscar", ".contcar"}
VALID_LEVELS = {"must_have", "useful", "supplementary"}


FIGURE_INTENT_PROMPT = """You are an expert in computational chemistry and density functional theory (DFT) for heterogeneous catalysis.
Your task is to identify the conventional figure types that are directly supported by the provided computational workflow.

The input consists only of:

- models
- methods
- adsorption_sites
- procedures

These describe the computational work that was actually performed.

Your objective is to recommend only academically standard figure types that are widely accepted in computational chemistry literature.

Strict rules:

1. Only recommend figures that are directly supported by the provided workflow.

2. Do NOT infer calculations that are not explicitly planned.

3. Do NOT recommend figures requiring:
   - experimental characterization
   - experimental performance plots
   - any unsupported descriptor

4. Do NOT over-interpret the workflow.
   If a figure cannot be generated directly from the described calculations, do not recommend it.

5. Prefer figure types that are considered conventional or standard in computational chemistry and DFT catalysis papers.

6. Figure names should be generic rather than project-specific.
   For example:
   - Computational model structures
   - Free-energy diagram
   - Adsorption free-energy comparison
   - Projected density of states
   - Charge density difference
   - Bader charge analysis
   - Local geometry analysis

7. Classify each figure using exactly one level:

- must_have
- useful
- supplementary

Definitions:

must_have
    Standard figures that are generally expected for the described computational workflow.

useful
    Commonly accepted figures that strengthen interpretation but are not essential.

supplementary
    Figures that are typically placed in Supporting Information or used only for completeness.

Return JSON only.

Schema:

{
  "figures": [
    {
      "figure_type": "<standard computational chemistry figure name>",
      "level": "must_have | useful | supplementary"
    }
  ]
}
"""


FIGURE_ROUTES = [
    {
        "type": "structure-grid",
        "skill": "adsorbate-structure-grid",
        "keywords": [
            "optimized adsorption configuration",
            "optimized adsorption configurations",
            "adsorption configuration",
            "adsorption configurations",
            "optimized adsorbate",
            "adsorbate configuration",
            "adsorbate structures",
        ],
        "role_any": ["adsorbate_relaxation_matrix"],
        "text_any": ["relax", "adsorbate", "adsorption", "configuration", "optimized"],
        "artifact_any": ["relax", ".traj", ".extxyz", "poscar", "contcar", ".vasp"],
    },
    {
        "type": "structure-grid",
        "skill": "adsorbate-structure-grid",
        "keywords": [
            "computational model",
            "model structure",
            "model structures",
            "structure",
            "slab",
            "active site",
            "adsorption site",
        ],
        "role_any": ["structure_model_build"],
        "text_any": ["build", "model", "structure", "slab", "site", "edge", "motif"],
        "artifact_any": [
            "poscar",
            "contcar",
            ".vasp",
            ".cif",
            ".xyz",
            ".extxyz",
            ".traj",
            "model_manifest",
            "model_metadata",
            "structure",
        ],
    },
    {
        "type": "energy-diagram",
        "skill": "energy-diagram-plotter",
        "keywords": [
            "free-energy diagram",
            "free energy diagram",
            "reaction free-energy",
            "reaction free energy",
            "reaction-step free-energy",
            "reaction step free-energy",
            "reaction-step free energy",
            "reaction energy profile",
            "energy profile",
            "reaction coordinate",
        ],
        "role_any": [
            "free_energy_diagram_assembly",
            "electrochemical_free_energy_bookkeeping",
            "potential_shift_analysis",
        ],
        "text_any": [
            "free-energy diagram",
            "free energy diagram",
            "relative free energies",
            "reaction coordinate",
            "potential",
        ],
        "artifact_any": [
            "energy_diagram",
            "free_energy",
            "relative_free_energies",
            "plot_spec",
            "state_table",
            "potential_shifted",
        ],
    },
    {
        "type": "descriptor-comparison",
        "skill": "nature-figure",
        "keywords": [
            "adsorption free-energy comparison",
            "adsorption free energy comparison",
            "adsorption energy comparison",
            "free-energy comparison",
            "free energy comparison",
            "descriptor comparison",
            "reaction descriptor",
            "thermodynamic descriptor",
            "thermodynamic limiting-step",
            "thermodynamic limiting step",
            "limiting-step comparison",
            "limiting step comparison",
        ],
        "role_any": ["descriptor_calculation"],
        "text_any": [
            "delta g",
            "deltag",
            "dg_",
            "adsorption free energy",
            "adsorption energy",
            "descriptor",
            "thermodynamic span",
            "largest uphill",
            "desorption free energy",
        ],
        "artifact_any": [
            "delta_g",
            "adsorption",
            "descriptor",
            "by_motif",
            "thermodynamic",
            "largest_uphill",
            "desorption",
        ],
    },
    {
        "type": "electronic-descriptor",
        "skill": "nature-figure",
        "keywords": [
            "projected density of states",
            "density of states",
            "projected dos",
            "pdos",
        ],
        "role_any": ["projected_dos_analysis"],
        "text_any": ["projected dos", "density of states", "pdos", "electronic"],
        "artifact_any": ["dos", "pdos", "projected"],
    },
    {
        "type": "electronic-descriptor",
        "skill": "nature-figure",
        "keywords": [
            "charge density difference",
            "charge transfer",
            "bader charge",
            "charge analysis",
        ],
        "role_any": ["charge_transfer_analysis"],
        "text_any": ["charge density", "charge transfer", "bader", "charge analysis"],
        "artifact_any": ["charge", "bader", "density"],
    },
    {
        "type": "calculation-diagnostic",
        "skill": "TASK_CALCULATION_RESULT_ANALYZER",
        "keywords": [
            "local geometry analysis",
            "geometry analysis",
            "bond length",
            "coordination",
            "relaxation",
            "relaxed structure",
        ],
        "role_any": ["relaxation_matrix", "adsorbate_relaxation_matrix", "geometry_analysis"],
        "text_any": ["relax", "geometry", "bond", "coordination", "distance"],
        "artifact_any": ["analysis_summary", "evidence_readiness", "metrics", "relax", "geometry", ".traj", ".extxyz"],
    },
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_default_env() -> None:
    cwd = Path.cwd()
    for path in (cwd / ".env", cwd / "DEPENDENCY" / ".env"):
        load_env_file(path)


def load_json_or_python(path: Path) -> Any:
    text = read_text(path)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    tree = ast.parse(text, filename=str(path))
    candidates: list[Any] = []
    preferred = {
        "selected_strategy",
        "generated_strategies",
        "strategy_generation",
        "strategies",
        "result",
        "data",
    }
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if any(name in preferred for name in names):
                return ast.literal_eval(node.value)
            if names:
                candidates.append(node.value)
    if candidates:
        return ast.literal_eval(candidates[0])
    raise ValueError(f"Could not load JSON or literal assignment from {path}")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def text_blob(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return " ".join(text_blob(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(text_blob(v) for v in value)
    return str(value)


def norm(value: Any) -> str:
    return text_blob(value).lower()


def unique(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for value in values:
        key = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return value or "figure"


def extract_strategy(data: Any, strategy_id: str | None) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("selected_strategy"), dict):
        return data["selected_strategy"]
    if isinstance(data, dict) and data.get("strategy_id"):
        return data

    candidates: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for key in ("strategies", "generated_strategies", "items"):
            if isinstance(data.get(key), list):
                candidates.extend(x for x in data[key] if isinstance(x, dict))
        for value in data.values():
            if isinstance(value, dict) and value.get("strategy_id"):
                candidates.append(value)
    elif isinstance(data, list):
        candidates.extend(x for x in data if isinstance(x, dict))

    if strategy_id:
        for candidate in candidates:
            if candidate.get("strategy_id") == strategy_id:
                return candidate
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError("Could not determine selected strategy; pass --strategy-id")


def computational_block(strategy: dict[str, Any]) -> dict[str, Any]:
    experiment = strategy.get("experiment")
    if isinstance(experiment, dict) and isinstance(experiment.get("computational"), dict):
        return experiment["computational"]
    return strategy


def strategy_figure_input(strategy: dict[str, Any]) -> dict[str, Any]:
    computational = computational_block(strategy)
    dft_details = computational.get("dft_details") if isinstance(computational.get("dft_details"), dict) else {}
    fallback_dft = strategy.get("dft_details") if isinstance(strategy.get("dft_details"), dict) else {}
    return {
        "models": as_list(computational.get("models") or strategy.get("models")),
        "methods": as_list(computational.get("methods") or strategy.get("methods")),
        "adsorption_sites": as_list(dft_details.get("adsorption_sites") or fallback_dft.get("adsorption_sites")),
        "procedures": as_list(computational.get("procedures") or strategy.get("procedures")),
    }


def strategy_claim(strategy: dict[str, Any]) -> str:
    for path in (
        ("hypothesis", "statement"),
        ("conclusion", "statement"),
        ("problem", "question"),
        ("title",),
    ):
        node: Any = strategy
        for key in path:
            if not isinstance(node, dict) or key not in node:
                node = None
                break
            node = node[key]
        if isinstance(node, str) and node.strip():
            text = " ".join(node.split())
            return text[:360]
    return ""


def recipe_entries(recipe_root: Path, recipe_index: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for procedure in recipe_index.get("procedures", []):
        if not isinstance(procedure, dict):
            continue
        pid = str(procedure.get("procedure_id", ""))
        p_folder = str(procedure.get("folder", ""))
        source_text = str(procedure.get("source_text", ""))
        for calc in procedure.get("calculations", []):
            if not isinstance(calc, dict):
                continue
            cid = str(calc.get("calculation_id", ""))
            folder = str(calc.get("folder", ""))
            calc_dir = recipe_root / folder
            manifest_path = calc_dir / "execution" / "execution_manifest.json"
            manifest: dict[str, Any] | None = None
            if manifest_path.exists():
                loaded = load_json_or_python(manifest_path)
                if isinstance(loaded, dict):
                    manifest = loaded
            entries.append(
                {
                    "procedure_id": pid,
                    "procedure_folder": p_folder,
                    "procedure_text": source_text,
                    "calculation_id": cid,
                    "calculation_ref": f"{pid}/{cid}" if pid and cid else cid or pid,
                    "calculation_title": str(calc.get("calculation_title", "")),
                    "recipe_role": str(calc.get("recipe_role", "")),
                    "folder": folder,
                    "calc_dir": str(calc_dir),
                    "manifest_path": str(manifest_path) if manifest_path.exists() else "",
                    "manifest": manifest,
                }
            )
    return entries


def entry_status(entry: dict[str, Any]) -> str:
    manifest = entry.get("manifest")
    if not isinstance(manifest, dict):
        return "missing"
    status = manifest.get("acceptance_state") or manifest.get("validation_status") or "missing"
    status = str(status)
    if status not in STATUS_ORDER:
        if "accept" in status:
            return "accepted-with-caveat"
        if "fail" in status:
            return "failed"
        if "exclude" in status:
            return "excluded"
        if "unsupported" in status:
            return "unsupported"
        return "missing"
    return status


def entry_artifacts(entry: dict[str, Any]) -> list[str]:
    manifest = entry.get("manifest")
    if not isinstance(manifest, dict):
        return []
    artifacts: list[str] = []
    for key in ("output_artifacts", "input_artifacts"):
        values = manifest.get(key)
        if isinstance(values, list):
            artifacts.extend(str(value) for value in values)
    return unique(artifacts)


def entry_caveats(entry: dict[str, Any]) -> list[str]:
    manifest = entry.get("manifest")
    if not isinstance(manifest, dict):
        return []
    return [str(item) for item in as_list(manifest.get("caveats")) if str(item).strip()]


def source_basis(entries: list[dict[str, Any]], limit: int = 3) -> list[str]:
    basis: list[str] = []
    by_proc: dict[str, str] = {}
    for entry in entries:
        pid = str(entry.get("procedure_id", ""))
        text = " ".join(str(entry.get("procedure_text", "")).split())
        if pid and text and pid not in by_proc:
            by_proc[pid] = text
    for pid, text in sorted(by_proc.items()):
        basis.append(f"{pid}: {text[:280]}")
        if len(basis) >= limit:
            break
    return basis


def status_for_entries(entries: list[dict[str, Any]]) -> str:
    statuses = [entry_status(entry) for entry in entries]
    if not statuses:
        return "blocked"
    if all(status in BAD_STATUSES for status in statuses):
        return "blocked"
    worst = max(statuses, key=lambda status: STATUS_ORDER.get(status, 99))
    if worst in BAD_STATUSES:
        return "accepted-with-caveat"
    return worst


def artifact_sort_key(path: str) -> tuple[int, int, str]:
    lower = path.lower()
    name = Path(lower).name
    suffix = Path(lower).suffix
    if name in {"poscar", "contcar"} or suffix in STRUCTURE_EXTS:
        return (-1, len(path), path)
    return (EXT_PRIORITY.get(suffix, 9), len(path), path)


def blockers_for_entries(entries: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for entry in entries:
        status = entry_status(entry)
        if status == "missing":
            blockers.append(f"{entry['calculation_ref']} has no execution_manifest.json")
        elif status in {"failed", "excluded", "unsupported"}:
            reason = "; ".join(entry_caveats(entry)) or status
            blockers.append(f"{entry['calculation_ref']} is {status}: {reason}")
    return unique(blockers)


def build_prompt(strategy_input: dict[str, Any]) -> str:
    return f"{FIGURE_INTENT_PROMPT}\n\nComputational workflow input:\n{json.dumps(strategy_input, indent=2)}\n"


def build_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
    }


def call_openai(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"OpenAI API request failed: {exc.reason}") from exc


def output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def parse_json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM figure intent output must be a JSON object.")
    return data


def normalize_level(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "musthave": "must_have",
        "must_have": "must_have",
        "required": "must_have",
        "essential": "must_have",
        "main": "must_have",
        "useful": "useful",
        "supporting": "useful",
        "optional": "useful",
        "supplementary": "supplementary",
        "si": "supplementary",
        "supporting_information": "supplementary",
    }
    return aliases.get(text, text)


def normalize_intents(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw = payload.get("figures")
    if not isinstance(raw, list):
        raise ValueError("LLM figure intent JSON must contain a figures list.")
    intents: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        figure_type = " ".join(str(item.get("figure_type", "")).split())
        level = normalize_level(item.get("level"))
        if not figure_type or level not in VALID_LEVELS:
            continue
        intents.append({"figure_type": figure_type, "level": level})
    return unique(intents)


def load_intents(path: Path) -> list[dict[str, str]]:
    payload = load_json_or_python(path)
    if isinstance(payload, dict) and "figures" in payload:
        return normalize_intents(payload)
    if isinstance(payload, dict):
        text = output_text(payload)
        if text:
            return normalize_intents(parse_json_text(text))
    raise ValueError(f"Could not load figure intents from {path}")


def route_for_figure_type(figure_type: str) -> dict[str, Any]:
    text = figure_type.lower()
    for route in FIGURE_ROUTES:
        if any(keyword in text for keyword in route["keywords"]):
            return route
    words = [word for word in re.split(r"[^a-z0-9]+", text) if len(word) > 3]
    return {
        "type": slug(figure_type),
        "skill": "",
        "keywords": words,
        "role_any": [],
        "text_any": words,
        "artifact_any": words,
    }


def entry_matches_route(entry: dict[str, Any], route: dict[str, Any]) -> bool:
    role_terms = {str(item).lower() for item in route.get("role_any", [])}
    text_terms = [str(item).lower() for item in route.get("text_any", [])]
    artifact_terms = [str(item).lower() for item in route.get("artifact_any", [])]
    role = norm(entry.get("recipe_role"))
    if role_terms:
        return role in role_terms
    text = norm([entry.get("procedure_text", ""), entry.get("calculation_title", "")])
    artifacts = norm([Path(artifact).name for artifact in entry_artifacts(entry)])
    return (
        bool(text_terms and any(term in text for term in text_terms))
        or bool(artifact_terms and any(term in artifacts for term in artifact_terms))
    )


def matching_entries(entries: list[dict[str, Any]], route: dict[str, Any]) -> list[dict[str, Any]]:
    matched = [entry for entry in entries if entry_matches_route(entry, route)]
    return unique(matched)


def keep_route_artifacts(route: dict[str, Any], entries: list[dict[str, Any]], limit: int) -> list[str]:
    artifacts = [artifact for entry in entries for artifact in entry_artifacts(entry)]
    terms = [str(item).lower() for item in route.get("artifact_any", [])]
    if terms:
        kept = [artifact for artifact in artifacts if any(term in Path(artifact).name.lower() for term in terms)]
    else:
        kept = artifacts
    if not kept:
        kept = artifacts
    return sorted(unique(kept), key=artifact_sort_key)[:limit]


def species_token(raw: str) -> str:
    token = raw.strip().lower()
    token = token.replace("*", "")
    token = re.sub(r"[^a-z0-9]+", "_", token).strip("_")
    return token


def extract_quantities_from_text(text: str) -> list[str]:
    quantities: list[str] = []
    lower = text.lower()
    if "free-energy diagram" in lower or "free energy diagram" in lower or "relative free energies" in lower:
        quantities.append("free_energy_profile")
    if "potential" in lower:
        quantities.append("potential_shift")
    if "thermodynamic span" in lower:
        quantities.append("thermodynamic_span_ev")
    if "largest uphill" in lower:
        quantities.append("largest_uphill_step_ev")
    if "projected dos" in lower or "projected density of states" in lower or "pdos" in lower:
        quantities.append("projected_dos")
    if "charge transfer" in lower:
        quantities.append("charge_transfer")
    if "bader" in lower:
        quantities.append("bader_charge")
    if "charge density difference" in lower:
        quantities.append("charge_density_difference")
    if "local geometry" in lower or "geometry analysis" in lower:
        quantities.append("local_geometry")
    for match in re.finditer(r"(?:delta\s*g|deltag|dg|Δg|∆g)\s*[_-]\s*([a-zA-Z0-9]+)", text, flags=re.IGNORECASE):
        token = species_token(match.group(1))
        if token and token not in {"e", "ev"}:
            quantities.append(f"delta_g_{token}_ev")
    for match in re.finditer(r"([A-Za-z0-9]+)\\*?\\s+desorption free energy", text, flags=re.IGNORECASE):
        token = species_token(match.group(1))
        if token:
            quantities.append(f"{token}_desorption_free_energy_ev")
    return unique(quantities)


def grounding_for_intent(route: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    text = text_blob([entry.get("procedure_text", "") for entry in entries] + [entry.get("calculation_title", "") for entry in entries])
    quantities = extract_quantities_from_text(text)
    if not quantities:
        quantities = [str(route.get("type", "figure"))]
    return {
        "status": "grounded" if entries else "blocked",
        "quantities": quantities,
        "basis": source_basis(entries),
    }


def build_figures(
    strategy: dict[str, Any],
    recipe_index: dict[str, Any],
    recipe_root: Path,
    intents: list[dict[str, str]],
    artifact_limit: int,
) -> dict[str, Any]:
    strategy_id = str(strategy.get("strategy_id") or recipe_index.get("strategy_id") or "")
    claim = strategy_claim(strategy)
    entries = recipe_entries(recipe_root, recipe_index)

    figures: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for idx, intent in enumerate(intents, start=1):
        route = route_for_figure_type(intent["figure_type"])
        matched_entries = matching_entries(entries, route)
        status = status_for_entries(matched_entries)
        artifacts = keep_route_artifacts(route, matched_entries, artifact_limit)
        grounding = grounding_for_intent(route, matched_entries)
        figure = {
            "id": f"F{idx}",
            "level": intent["level"],
            "figure_type": intent["figure_type"],
            "type": str(route.get("type", slug(intent["figure_type"]))),
            "title": intent["figure_type"],
            "claim": claim,
            "source": {
                "procedures": sorted({str(entry.get("procedure_id", "")) for entry in matched_entries if entry.get("procedure_id")}),
                "calculations": sorted({str(entry.get("calculation_ref", "")) for entry in matched_entries if entry.get("calculation_ref")}),
            },
            "artifacts": artifacts,
            "status": status,
            "skill": str(route.get("skill", "")),
            "grounding": grounding,
            "caveats": unique([caveat for entry in matched_entries for caveat in entry_caveats(entry)])[:8],
            "blockers": blockers_for_entries(matched_entries),
        }
        if not matched_entries:
            figure["blockers"].append("No explicit recipe procedure/calculation matched this LLM figure intent.")
        if status == "blocked" and not figure["blockers"]:
            figure["blockers"].append("All matched calculation evidence is missing, failed, excluded, or unsupported.")
        figures.append(figure)

    figures.sort(key=lambda item: (level_rank(item["level"]), item["id"]))
    for idx, figure in enumerate(figures, start=1):
        old_id = figure["id"]
        figure["id"] = f"F{idx}"
        for blocker in figure["blockers"]:
            blockers.append({"figure": figure["id"], "reason": blocker})

    return {
        "schema_version": 1,
        "mapper_mode": "llm_figure_intent",
        "strategy_id": strategy_id,
        "figures": figures,
        "blockers": blockers,
    }


def level_rank(level: str) -> int:
    order = {
        "must_have": 0,
        "useful": 1,
        "supplementary": 2,
        "main-claim": 0,
        "supporting-main": 1,
        "context-method": 2,
        "si-evidence": 3,
        "si-archive": 4,
    }
    return order.get(level, 9)


def markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"# Figure Mapping for {plan.get('strategy_id') or 'strategy'}",
        "",
        f"- Mapper mode: `{plan.get('mapper_mode', 'unknown')}`",
        "",
        "| ID | Level | Figure Type | Routed Type | Status | Skill | Source |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for fig in plan.get("figures", []):
        source = ", ".join(fig.get("source", {}).get("procedures", []))
        lines.append(
            f"| {fig['id']} | {fig['level']} | {fig['figure_type']} | {fig['type']} | {fig['status']} | {fig['skill']} | {source} |"
        )
    lines.extend(["", "## Details", ""])
    for fig in plan.get("figures", []):
        lines.append(f"### {fig['id']} - {fig['figure_type']}")
        lines.append(f"- Level: `{fig['level']}`")
        lines.append(f"- Routed type: `{fig['type']}`")
        lines.append(f"- Status: `{fig['status']}`")
        lines.append(f"- Skill: `{fig['skill']}`")
        lines.append(f"- Source procedures: {', '.join(fig.get('source', {}).get('procedures', [])) or 'none'}")
        lines.append(f"- Source calculations: {', '.join(fig.get('source', {}).get('calculations', [])) or 'none'}")
        if fig.get("claim"):
            lines.append(f"- Claim: {fig['claim']}")
        if fig.get("grounding"):
            grounding = fig["grounding"]
            quantities = ", ".join(grounding.get("quantities", [])) or "none"
            lines.append(f"- Grounding: `{grounding.get('status', 'unknown')}`; quantities: {quantities}")
            for basis in grounding.get("basis", [])[:2]:
                lines.append(f"  - {basis}")
        if fig.get("artifacts"):
            lines.append("- Artifacts:")
            for artifact in fig["artifacts"]:
                lines.append(f"  - `{artifact}`")
        if fig.get("caveats"):
            lines.append("- Caveats:")
            for caveat in fig["caveats"]:
                lines.append(f"  - {caveat}")
        if fig.get("blockers"):
            lines.append("- Blockers:")
            for blocker in fig["blockers"]:
                lines.append(f"  - {blocker}")
        lines.append("")
    if plan.get("blockers"):
        lines.extend(["## Blockers", ""])
        for blocker in plan["blockers"]:
            lines.append(f"- {blocker['figure']}: {blocker['reason']}")
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ask an LLM for generic strategy figure intents and attach explicit recipe evidence."
    )
    parser.add_argument("--strategy", required=True, help="selected_strategy.json or compatible strategy artifact.")
    parser.add_argument("--recipe-root", required=True, help="Strategy explicit recipe root containing recipe_index.json.")
    parser.add_argument("--strategy-id", help="Strategy ID to select when --strategy contains many strategies.")
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        help=f"OpenAI model. Defaults to OPENAI_MODEL or {DEFAULT_MODEL}.",
    )
    parser.add_argument("--intent-json", help="Use an existing LLM intent JSON/OpenAI response instead of calling the API.")
    parser.add_argument("--save-response", help="Write the full OpenAI response JSON.")
    parser.add_argument("--save-prompt", help="Write the exact LLM prompt for inspection.")
    parser.add_argument("--dry-run", action="store_true", help="Print the LLM prompt input and exit without calling the API.")
    parser.add_argument("--rules", help=argparse.SUPPRESS)
    parser.add_argument(
        "--outdir",
        help="Output directory for figure_info.json and figure_info.md. Overrides the default <strategy_id>_figure/mapping.",
    )
    parser.add_argument(
        "--figure-root",
        help="Strategy figure workspace root. Mapping is written to <figure-root>/mapping.",
    )
    parser.add_argument("--artifact-limit", type=int, default=12, help="Maximum artifacts kept per figure candidate.")
    return parser


def resolve_outdir(args: argparse.Namespace, recipe_root: Path, strategy_id: str) -> Path:
    if args.outdir and args.figure_root:
        raise SystemExit("Use either --outdir or --figure-root, not both.")
    if args.outdir:
        return Path(args.outdir)
    if args.figure_root:
        return Path(args.figure_root) / "mapping"
    figure_root = recipe_root.parent / f"{strategy_id}_figure"
    return figure_root / "mapping"


def main() -> int:
    load_default_env()
    parser = build_parser()
    args = parser.parse_args()

    strategy_path = Path(args.strategy)
    recipe_root = Path(args.recipe_root)
    recipe_index_path = recipe_root / "recipe_index.json"
    if not recipe_index_path.exists():
        raise SystemExit(f"Missing recipe_index.json: {recipe_index_path}")

    strategy_payload = load_json_or_python(strategy_path)
    recipe_index = load_json_or_python(recipe_index_path)
    strategy_id = args.strategy_id or (recipe_index.get("strategy_id") if isinstance(recipe_index, dict) else None)
    strategy = extract_strategy(strategy_payload, strategy_id)
    strategy_input = strategy_figure_input(strategy)
    prompt = build_prompt(strategy_input)

    if args.save_prompt:
        Path(args.save_prompt).write_text(prompt, encoding="utf-8")
    if args.dry_run:
        print(
            json.dumps(
                {
                    "model": args.model,
                    "strategy_id": strategy_id,
                    "strategy_input": strategy_input,
                    "will_call_api": False,
                    "prompt": prompt,
                },
                indent=2,
            )
        )
        return 0

    if args.intent_json:
        intents = load_intents(Path(args.intent_json))
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY is not set. Export it or provide --intent-json.")
        response = call_openai(build_payload(args.model, prompt), api_key)
        if args.save_response:
            Path(args.save_response).write_text(json.dumps(response, indent=2), encoding="utf-8")
        text = output_text(response)
        if not text:
            raise SystemExit("No text output found in OpenAI response.")
        intents = normalize_intents(parse_json_text(text))

    if not intents:
        raise SystemExit("No supported figure intents were returned.")

    plan = build_figures(strategy, recipe_index, recipe_root, intents, args.artifact_limit)
    outdir = resolve_outdir(args, recipe_root, str(plan.get("strategy_id") or strategy_id or "strategy"))
    write_json(outdir / "figure_info.json", plan)
    (outdir / "figure_info.md").write_text(markdown(plan), encoding="utf-8")
    print(f"Wrote {outdir / 'figure_info.json'}")
    print(f"Wrote {outdir / 'figure_info.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
