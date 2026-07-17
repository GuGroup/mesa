#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1
API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.5"
FORBIDDEN_DECISION_FIELDS = {
    "status",
    "blocked",
    "unsupported",
    "executable",
    "feasible",
    "requires_repair",
    "reason",
    "why_cannot_be_done",
}

CANONICAL_RECIPE_ROLES = {
    "adsorbate_relaxation_matrix",
    "benchmark_constraint_comparison",
    "charge_transfer_analysis",
    "clean_structure_relaxation",
    "density_of_states_analysis",
    "descriptor_calculation",
    "electrochemical_free_energy_bookkeeping",
    "free_energy_diagram_assembly",
    "free_energy_state_definition",
    "potential_shift_analysis",
    "projected_dos_analysis",
    "structure_model_build",
}


@dataclass(frozen=True)
class ComputationalSource:
    strategy: dict[str, Any]
    computational: dict[str, Any]
    pointer: str
    strategy_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Translate a selected strategy computational section into a "
            "procedure-indexed explicit calculation recipe tree."
        )
    )
    parser.add_argument("--strategy", required=True, type=Path, help="Selected strategy JSON artifact.")
    parser.add_argument("--out", required=True, type=Path, help="Output recipe directory.")
    parser.add_argument("--force", action="store_true", help="Replace an existing output directory.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL), help="Model used only for unclassified procedures.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"strategy artifact is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"strategy artifact must be a JSON object: {path}")
    return data


def load_env() -> None:
    for path in (Path.cwd() / ".env", Path.cwd() / "DEPENDENCY/.env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def find_computational_section(data: dict[str, Any]) -> ComputationalSource:
    roots: list[tuple[dict[str, Any], str]] = []
    if isinstance(data.get("selected_strategy"), dict):
        roots.append((data["selected_strategy"], "/selected_strategy"))
    roots.append((data, ""))

    for root, root_pointer in roots:
        for experiment_key in ("experiment", "experimental"):
            experiment = root.get(experiment_key)
            if isinstance(experiment, dict) and isinstance(experiment.get("computational"), dict):
                pointer = f"{root_pointer}/{experiment_key}/computational" if root_pointer else f"/{experiment_key}/computational"
                return ComputationalSource(root, experiment["computational"], pointer, str(root.get("strategy_id", "")))
        if isinstance(root.get("computational"), dict):
            pointer = f"{root_pointer}/computational" if root_pointer else "/computational"
            return ComputationalSource(root, root["computational"], pointer, str(root.get("strategy_id", "")))

    raise SystemExit(
        "could not find experiment.computational, experimental.computational, or computational in strategy artifact"
    )


def slugify(text: str, max_length: int = 72) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = "item"
    return slug[:max_length].strip("_") or "item"


def write_json(path: Path, data: dict[str, Any], *, check_decision_fields: bool = False) -> None:
    if check_decision_fields:
        assert_no_decision_fields(data, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def assert_no_decision_fields(value: Any, path: Path) -> None:
    if isinstance(value, dict):
        overlap = FORBIDDEN_DECISION_FIELDS.intersection(value)
        if overlap:
            forbidden = ", ".join(sorted(overlap))
            raise SystemExit(f"internal error: forbidden decision field(s) {forbidden} would be written to {path}")
        for child in value.values():
            assert_no_decision_fields(child, path)
    elif isinstance(value, list):
        for child in value:
            assert_no_decision_fields(child, path)


def source_context(computational: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key in (
        "models",
        "methods",
        "dft_details",
        "computational_tests_to_run",
        "computational_benchmark_comparisons",
    ):
        if key in computational:
            context[key] = computational[key]
    return context


def list_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def split_models_from_build_procedure(text: str) -> list[str]:
    match = re.search(
        r"(?:build|construct|create|generate)\s+(?:the\s+)?(?:clean\s+)?(.+?)\s+model(?:\s+set|s)?\.?$",
        text,
        flags=re.I,
    )
    if not match:
        return []
    body = match.group(1)
    body = body.replace(", and ", ", ")
    body = body.replace(" and ", ", ")
    return [part.strip(" .") for part in body.split(",") if part.strip(" .")]


STATE_LIST_MARKER_RE = re.compile(
    r"(?:"
    r"explicit(?:\s+alkaline)?(?:\s+her)?(?:\s+free[- ]energy)?(?:\s+diagram)?\s+states"
    r"|full\s+alkaline\s+her\s+free[- ]energy\s+diagram\s+states"
    r"|free[- ]energy\s+diagram\s+states"
    r")\s*:\s*",
    flags=re.I,
)


def split_explicit_states(text: str) -> list[str]:
    if STATE_LIST_MARKER_RE.search(text) is None:
        return []
    body = STATE_LIST_MARKER_RE.split(text, maxsplit=1)[1]
    return [part.strip(" .") for part in body.split(";") if part.strip(" .")]


def split_descriptor_names(text: str) -> list[str]:
    match = re.search(r"calculate (.+?) for each motif", text, flags=re.I)
    if not match:
        return []
    body = match.group(1)
    body = body.replace(", and ", ", ")
    body = body.replace(" and ", ", ")
    return [part.strip(" .") for part in body.split(",") if part.strip(" .")]


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def is_model_build_procedure(lower: str) -> bool:
    return contains_any(lower, ("build", "construct", "create", "generate")) and contains_any(
        lower, ("model", "slab", "surface structure")
    ) and not contains_any(lower, ("free-energy diagram", "free energy diagram", "energy profile"))


def is_adsorbate_relaxation_procedure(lower: str) -> bool:
    if not contains_any(lower, ("relax", "optimize", "optimise")):
        return False
    return contains_any(
        lower,
        (
            "adsorbate",
            "adsorbed",
            "adsorption state",
            "h2o*",
            "oh*",
            "h*",
            "i0",
            "i1",
            "i2",
            "i3",
            "i4",
        ),
    )


def is_clean_relaxation_procedure(lower: str) -> bool:
    return contains_any(lower, ("relax", "optimize", "optimise")) and "clean" in lower and contains_any(
        lower, ("structure", "model", "slab", "surface")
    )


def requests_dos(lower: str) -> bool:
    return bool(re.search(r"\b(?:projected\s+)?dos\b", lower)) or "density of states" in lower


def requests_charge_analysis(lower: str) -> bool:
    return contains_any(
        lower,
        ("charge transfer", "charge-transfer", "charge density", "charge-density", "bader charge"),
    )


def is_free_energy_diagram_procedure(lower: str) -> bool:
    has_free_energy = "free-energy" in lower or "free energy" in lower
    has_figure_object = contains_any(lower, ("diagram", "profile", "reaction coordinate"))
    return has_free_energy and has_figure_object


def is_descriptor_comparison_procedure(lower: str) -> bool:
    return contains_any(
        lower,
        (
            "maximum uphill",
            "largest uphill",
            "thermodynamic step",
            "limiting step",
            "descriptor comparison",
            "compare descriptors",
            "thermodynamic ranking",
        ),
    )


def response_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def parse_role_decisions(text: str, source_text: str) -> list[dict[str, str]]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    payload = json.loads(text)
    raw = payload.get("roles") if isinstance(payload, dict) else None
    if not isinstance(raw, list) or not raw:
        raise ValueError("LLM role output must contain a non-empty roles list")
    source_normalized = " ".join(source_text.split()).casefold()
    decisions: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each LLM role decision must be an object")
        role = str(item.get("recipe_role", "")).strip()
        phrase = " ".join(str(item.get("source_phrase", "")).split())
        if role not in CANONICAL_RECIPE_ROLES:
            raise ValueError(f"LLM returned unknown recipe_role: {role!r}")
        if not phrase or phrase.casefold() not in source_normalized:
            raise ValueError(f"LLM source_phrase is not present in the procedure: {phrase!r}")
        decision = {"recipe_role": role, "source_phrase": phrase}
        if decision not in decisions:
            decisions.append(decision)
    return decisions


def classify_roles_with_llm(source_text: str, computational: dict[str, Any], model: str) -> list[dict[str, str]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required because a procedure could not be classified deterministically")
    prompt = {
        "task": "Select the calculation roles explicitly requested by the procedure.",
        "allowed_recipe_roles": sorted(CANONICAL_RECIPE_ROLES),
        "rules": [
            "Return only roles explicitly supported by the procedure.",
            "Use an exact source_phrase copied from the procedure for every role.",
            "Do not judge feasibility and do not invent calculations.",
            "Return JSON only as {\"roles\":[{\"recipe_role\":\"...\",\"source_phrase\":\"...\"}]}",
        ],
        "procedure": source_text,
        "context": source_context(computational),
    }
    body = json.dumps({
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": json.dumps(prompt)}]}],
    }).encode()
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"OpenAI API HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"OpenAI API request failed: {exc.reason}") from exc
    return parse_role_decisions(response_text(result), source_text)


def recipe(
    *,
    strategy_id: str,
    procedure_id: str,
    calculation_id: str,
    source_text: str,
    pointer: str,
    role: str,
    title: str,
    required_prior_artifacts: list[str],
    required_inputs: list[str],
    operations: list[str],
    method_intent: list[str],
    output_artifacts: list[str],
    notes: list[str] | None = None,
    source_terms: dict[str, Any] | None = None,
    source_phrase: str | None = None,
) -> dict[str, Any]:
    if role not in CANONICAL_RECIPE_ROLES:
        allowed = ", ".join(sorted(CANONICAL_RECIPE_ROLES))
        raise ValueError(f"unknown recipe_role {role!r}; expected one of: {allowed}")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "procedure_id": procedure_id,
        "calculation_id": calculation_id,
        "source_json_pointer": pointer,
        "source_procedure_text": source_text,
        "recipe_role": role,
        "calculation_title": title,
        "required_prior_artifacts": required_prior_artifacts,
        "required_inputs": required_inputs,
        "operations": operations,
        "method_intent": method_intent,
        "output_artifacts": output_artifacts,
        "source_terms": source_terms or {},
        "notes": notes or [],
    }
    if source_phrase:
        payload["source_phrase"] = source_phrase
    return payload


def build_recipes_for_procedure(
    strategy_id: str,
    procedure_id: str,
    pointer: str,
    source_text: str,
    computational: dict[str, Any],
    role_classifier: Callable[[str, dict[str, Any]], list[dict[str, str]]] | None = None,
) -> list[dict[str, Any]]:
    lower = source_text.lower()
    models = list_strings(computational.get("models"))
    adsorption_sites = list_strings(computational.get("dft_details", {}).get("adsorption_sites"))

    if is_model_build_procedure(lower):
        requested_models = split_models_from_build_procedure(source_text) or models or ["clean model set"]
        return [
            recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id=f"C{index:03d}",
                source_text=source_text,
                pointer=pointer,
                role="structure_model_build",
                title=f"Build clean model: {model}",
                required_prior_artifacts=["bulk_structure", "surface_orientation_or_edge_definition"],
                required_inputs=[model, "cell_size_policy", "termination_or_edge_policy"],
                operations=["construct_clean_surface_model", "write_structure_file", "write_model_metadata"],
                method_intent=["clean_slab_or_edge_model_construction"],
                output_artifacts=["clean_structure.vasp", "model_metadata.json"],
                source_terms={"model": model},
            )
            for index, model in enumerate(requested_models, start=1)
        ]

    if is_adsorbate_relaxation_procedure(lower):
        return [
            recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id="C001",
                source_text=source_text,
                pointer=pointer,
                role="adsorbate_relaxation_matrix",
                title="Relax adsorbate-bearing state matrix",
                required_prior_artifacts=["clean_structure_files", "adsorbate_placement_structures", "shared_relaxation_settings"],
                required_inputs=adsorption_sites or ["adsorbate_state_matrix"],
                operations=[
                    "prepare_adsorbate_relaxation_inputs",
                    "relax_adsorbate_bearing_structures",
                    "record_relaxed_adsorbate_outputs",
                ],
                method_intent=["adsorbate_geometry_optimization"],
                output_artifacts=["relaxed_adsorbate_structure_files", "adsorbate_relaxation_registry.json"],
            ),
        ]

    clean_relaxation = is_clean_relaxation_procedure(lower)
    dos_requested = requests_dos(lower)
    charge_requested = requests_charge_analysis(lower)
    if clean_relaxation or (dos_requested and not charge_requested):
        recipes: list[dict[str, Any]] = []
        if clean_relaxation:
            recipes.append(
                recipe(
                    strategy_id=strategy_id,
                    procedure_id=procedure_id,
                    calculation_id=f"C{len(recipes) + 1:03d}",
                    source_text=source_text,
                    pointer=pointer,
                    role="clean_structure_relaxation",
                    title="Relax clean-state model matrix",
                    required_prior_artifacts=["clean_structure_files", "shared_relaxation_settings"],
                    required_inputs=models or ["model_matrix"],
                    operations=[
                        "prepare_clean_relaxation_inputs",
                        "relax_clean_structures",
                        "record_relaxed_clean_outputs",
                    ],
                    method_intent=["geometry_optimization"],
                    output_artifacts=["relaxed_clean_structure_files", "clean_relaxation_registry.json"],
                )
            )
        if dos_requested:
            projected = "projected dos" in lower or "projected density of states" in lower or "pdos" in lower
            recipes.append(
                recipe(
                    strategy_id=strategy_id,
                    procedure_id=procedure_id,
                    calculation_id=f"C{len(recipes) + 1:03d}",
                    source_text=source_text,
                    pointer=pointer,
                    role="projected_dos_analysis" if projected else "density_of_states_analysis",
                    title="Compute projected density of states" if projected else "Compute density of states",
                    required_prior_artifacts=["relaxed_structures", "electronic_structure_data"],
                    required_inputs=models or ["relaxed_model_matrix"],
                    operations=["compute_density_of_states", "write_dos_tables"],
                    method_intent=["projected_density_of_states_analysis" if projected else "density_of_states_analysis"],
                    output_artifacts=["density_of_states.csv", "density_of_states_summary.json"],
                )
            )
        return recipes

    states = split_explicit_states(source_text)
    if states:
        recipes = [
            recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id=f"C{index:03d}",
                source_text=source_text,
                pointer=pointer,
                role="free_energy_state_definition",
                title=f"Define free-energy state: {state}",
                required_prior_artifacts=["relaxed_surface_state_or_reference_structure", "reference_species_policy"],
                required_inputs=[state],
                operations=["map_surface_state", "map_gas_or_solution_references", "assign_electron_reference_terms"],
                method_intent=["alkaline_free_energy_state_bookkeeping"],
                output_artifacts=["state_definition.json"],
                source_terms={"state_text": state},
            )
            for index, state in enumerate(states, start=1)
        ]
        recipes.append(
            recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id=f"C{len(recipes) + 1:03d}",
                source_text=source_text,
                pointer=pointer,
                role="free_energy_diagram_assembly",
                title="Assemble explicit alkaline free-energy diagram",
                required_prior_artifacts=["state_definition_json_files", "state_energy_records", "reference_energy_records"],
                required_inputs=["ordered_free_energy_states"],
                operations=["assemble_ordered_state_table", "write_diagram_input_table"],
                method_intent=["alkaline_free_energy_diagram_construction"],
                output_artifacts=["alkaline_free_energy_state_table.json", "alkaline_free_energy_diagram_inputs.csv"],
            )
        )
        return recipes

    if is_free_energy_diagram_procedure(lower):
        return [
            recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id="C001",
                source_text=source_text,
                pointer=pointer,
                role="free_energy_diagram_assembly",
                title="Assemble explicit free-energy diagram",
                required_prior_artifacts=["state_energy_records", "reference_energy_records", "zpe_entropy_records"],
                required_inputs=["ordered_free_energy_states", source_text],
                operations=["assemble_ordered_state_table", "write_diagram_input_table"],
                method_intent=["free_energy_diagram_construction"],
                output_artifacts=["free_energy_state_table.json", "free_energy_diagram_inputs.csv"],
            )
        ]

    if "relative free energies" in lower or "ph 14" in lower or "v_rhe" in lower:
        return [
            recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id="C001",
                source_text=source_text,
                pointer=pointer,
                role="electrochemical_free_energy_bookkeeping",
                title="Compute pH 14 U=0 V_RHE relative free energies",
                required_prior_artifacts=["state_energy_records", "reference_energy_records", "zpe_entropy_records"],
                required_inputs=["pH=14", "U=0 V_RHE", "electron_step_definitions", "reference_convention"],
                operations=["apply_pH_reference_terms", "apply_U_RHE_reference_terms", "compute_relative_free_energy_table"],
                method_intent=["pH_and_potential_dependent_free_energy_bookkeeping"],
                output_artifacts=["pH14_U0_relative_free_energies.json", "pH14_U0_relative_free_energies.csv"],
            ),
            recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id="C002",
                source_text=source_text,
                pointer=pointer,
                role="potential_shift_analysis",
                title="Apply optional potential shifts to electron steps",
                required_prior_artifacts=["pH14_U0_relative_free_energies.json"],
                required_inputs=["applied_potential_grid", "electron_step_definitions"],
                operations=["shift_electron_steps_by_potential", "write_potential_shifted_profiles"],
                method_intent=["applied_potential_sensitivity"],
                output_artifacts=["potential_shifted_free_energy_profiles.json"],
            ),
        ]

    descriptors = split_descriptor_names(source_text)
    if descriptors:
        return [
            recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id=f"C{index:03d}",
                source_text=source_text,
                pointer=pointer,
                role="descriptor_calculation",
                title=f"Calculate descriptor: {descriptor}",
                required_prior_artifacts=["free_energy_profile_table", "relaxed_state_energy_records"],
                required_inputs=[descriptor, "motif_index"],
                operations=["compute_descriptor_for_each_motif", "write_descriptor_table"],
                method_intent=["thermodynamic_descriptor_analysis"],
                output_artifacts=[f"{slugify(descriptor, 40)}_by_motif.csv", f"{slugify(descriptor, 40)}_by_motif.json"],
                source_terms={"descriptor": descriptor},
            )
            for index, descriptor in enumerate(descriptors, start=1)
        ]

    if is_descriptor_comparison_procedure(lower):
        return [
            recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id="C001",
                source_text=source_text,
                pointer=pointer,
                role="descriptor_calculation",
                title="Compare thermodynamic descriptors across models",
                required_prior_artifacts=["free_energy_profile_table", "relaxed_state_energy_records"],
                required_inputs=["model_index", "thermodynamic_step_definitions"],
                operations=["compute_step_descriptors", "compare_descriptors_across_models", "write_descriptor_table"],
                method_intent=["thermodynamic_descriptor_analysis"],
                output_artifacts=["thermodynamic_descriptors_by_model.csv", "descriptor_comparison.json"],
            )
        ]

    projected_dos_requested = "projected dos" in lower or "projected density of states" in lower or "pdos" in lower
    if charge_requested or projected_dos_requested:
        target_match = re.search(r"for (.+?) to verify", source_text, flags=re.I)
        targets = []
        if target_match:
            body = target_match.group(1).replace(", and ", ", ").replace(" and ", ", ")
            targets = [item.strip(" .") for item in body.split(",") if item.strip(" .")]
        targets = targets or ["specified atoms and adsorbates"]
        recipes = []
        if charge_requested:
            recipes.append(
                recipe(
                    strategy_id=strategy_id,
                    procedure_id=procedure_id,
                    calculation_id=f"C{len(recipes) + 1:03d}",
                    source_text=source_text,
                    pointer=pointer,
                    role="charge_transfer_analysis",
                    title="Compute charge-transfer descriptors",
                    required_prior_artifacts=["relaxed_structures", "charge_density_or_partitionable_electronic_density"],
                    required_inputs=targets,
                    operations=["partition_charge_by_target", "compare_clean_and_adsorbate_states", "write_charge_transfer_table"],
                    method_intent=["charge_partitioning_analysis"],
                    output_artifacts=["charge_transfer_by_target.csv", "charge_transfer_summary.json"],
                    source_terms={"targets": targets},
                )
            )
        if projected_dos_requested:
            recipes.append(
                recipe(
                    strategy_id=strategy_id,
                    procedure_id=procedure_id,
                    calculation_id=f"C{len(recipes) + 1:03d}",
                    source_text=source_text,
                    pointer=pointer,
                    role="projected_dos_analysis",
                    title="Compute projected DOS descriptors",
                    required_prior_artifacts=["relaxed_structures", "wavefunction_or_projector_data", "electronic_dos_data"],
                    required_inputs=targets,
                    operations=["project_dos_by_target", "extract_band_centers_or_near_fermi_descriptors", "write_pdos_tables"],
                    method_intent=["projected_density_of_states_analysis"],
                    output_artifacts=["projected_dos_by_target.csv", "dos_descriptor_summary.json"],
                    source_terms={"targets": targets},
                )
            )
        return recipes

    if "benchmark" in lower or "overpotential" in lower or "tafel" in lower:
        return [
            recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id="C001",
                source_text=source_text,
                pointer=pointer,
                role="benchmark_constraint_comparison",
                title="Compare computed descriptors against experimental benchmark constraints",
                required_prior_artifacts=["descriptor_tables", "benchmark_constraint_records"],
                required_inputs=["overpotential_constraint", "Tafel_constraint", "computed_descriptor_rankings"],
                operations=["compare_rankings_to_benchmark_constraints", "write_qualitative_comparison"],
                method_intent=["benchmark_constraint_contextualization"],
                output_artifacts=["benchmark_constraint_comparison.md", "benchmark_constraint_comparison.json"],
            )
        ]

    classifier = role_classifier or (
        lambda text, context: classify_roles_with_llm(
            text,
            context,
            os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        )
    )
    decisions = classifier(source_text, computational)
    return [
        recipe(
            strategy_id=strategy_id,
            procedure_id=procedure_id,
            calculation_id=f"C{index:03d}",
            source_text=source_text,
            pointer=pointer,
            role=decision["recipe_role"],
            title=decision["source_phrase"].rstrip("."),
            required_prior_artifacts=["strategy_context"],
            required_inputs=[decision["source_phrase"]],
            operations=["execute_source_specified_calculation", "write_required_outputs"],
            method_intent=[decision["recipe_role"]],
            output_artifacts=[f"{decision['recipe_role']}_result"],
            source_terms={"source_phrase": decision["source_phrase"]},
            source_phrase=decision["source_phrase"],
        )
        for index, decision in enumerate(decisions, start=1)
    ]


def render_recipe_md(recipe_data: dict[str, Any]) -> str:
    lines = [
        f"# {recipe_data['calculation_id']} {recipe_data['calculation_title']}",
        "",
        f"- Procedure: `{recipe_data['procedure_id']}`",
        f"- Role: `{recipe_data['recipe_role']}`",
        f"- Source: `{recipe_data['source_json_pointer']}`",
    ]
    if recipe_data.get("source_phrase"):
        lines.append(f"- Source phrase: {recipe_data['source_phrase']}")
    lines.extend([
        "",
        "## Source Procedure",
        "",
        recipe_data["source_procedure_text"],
        "",
        "## Required Prior Artifacts",
        "",
    ])
    lines.extend(f"- {item}" for item in recipe_data["required_prior_artifacts"])
    lines.extend(["", "## Required Inputs", ""])
    lines.extend(f"- {item}" for item in recipe_data["required_inputs"])
    lines.extend(["", "## Operations", ""])
    lines.extend(f"- {item}" for item in recipe_data["operations"])
    lines.extend(["", "## Method Intent", ""])
    lines.extend(f"- {item}" for item in recipe_data["method_intent"])
    lines.extend(["", "## Output Artifacts", ""])
    lines.extend(f"- {item}" for item in recipe_data["output_artifacts"])
    return "\n".join(lines) + "\n"


def render_procedure_map(procedure_data: dict[str, Any], calculations: list[dict[str, Any]]) -> str:
    lines = [
        f"# {procedure_data['procedure_id']} Procedure Map",
        "",
        "## Source Procedure",
        "",
        procedure_data["source_text"],
        "",
        "## Generated Calculation Recipes",
        "",
    ]
    for calc in calculations:
        lines.append(f"- `{calc['calculation_id']}` {calc['calculation_title']}")
    return "\n".join(lines) + "\n"


def render_index_md(index_data: dict[str, Any]) -> str:
    lines = [
        "# Explicit Calculation Recipe Index",
        "",
        f"- Strategy ID: `{index_data['strategy_id']}`",
        f"- Computational source: `{index_data['computational_json_pointer']}`",
        f"- Procedure count: {index_data['procedure_count']}",
        "",
        "This artifact translates the strategy computational section into recipe folders. It does not evaluate feasibility.",
        "",
        "## Procedures",
        "",
    ]
    for procedure in index_data["procedures"]:
        lines.append(
            f"- `{procedure['procedure_id']}` {procedure['source_text']} "
            f"({procedure['calculation_count']} calculation recipes)"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    load_env()
    args = parse_args()
    strategy_path = args.strategy.resolve()
    out = args.out.resolve()
    data = load_json(strategy_path)
    source = find_computational_section(data)
    procedures = list_strings(source.computational.get("procedures"))
    if not procedures:
        raise SystemExit(f"computational section has no procedures list: {strategy_path}")

    if out.exists():
        if not args.force:
            raise SystemExit(f"output directory already exists; pass --force to replace it: {out}")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    write_json(out / "source_computational_section.json", source.computational)
    context = source_context(source.computational)
    index_records: list[dict[str, Any]] = []

    for proc_index, proc_text in enumerate(procedures, start=1):
        procedure_id = f"P{proc_index:03d}"
        proc_pointer = f"{source.pointer}/procedures/{proc_index - 1}"
        proc_folder = out / f"{procedure_id}_{slugify(proc_text)}"
        calculations_root = proc_folder / "calculations"
        calculations = build_recipes_for_procedure(
            source.strategy_id,
            procedure_id,
            proc_pointer,
            proc_text,
            source.computational,
            role_classifier=lambda text, context: classify_roles_with_llm(text, context, args.model),
        )

        calc_records: list[dict[str, str]] = []
        for calc in calculations:
            calc_folder = calculations_root / f"{calc['calculation_id']}_{slugify(calc['calculation_title'])}"
            write_json(calc_folder / "recipe.json", calc, check_decision_fields=True)
            write_text(calc_folder / "recipe.md", render_recipe_md(calc))
            calc_record = {
                "calculation_id": calc["calculation_id"],
                "folder": str(calc_folder.relative_to(out)),
                "calculation_title": calc["calculation_title"],
                "recipe_role": calc["recipe_role"],
            }
            if calc.get("source_phrase"):
                calc_record["source_phrase"] = calc["source_phrase"]
            calc_records.append(calc_record)

        procedure_data = {
            "schema_version": SCHEMA_VERSION,
            "strategy_id": source.strategy_id,
            "procedure_id": procedure_id,
            "source_json_pointer": proc_pointer,
            "source_text": proc_text,
            "source_context": context,
            "calculation_folders": calc_records,
        }
        write_json(proc_folder / "procedure.json", procedure_data)
        write_text(proc_folder / "procedure_map.md", render_procedure_map(procedure_data, calculations))

        index_records.append(
            {
                "procedure_id": procedure_id,
                "folder": str(proc_folder.relative_to(out)),
                "source_json_pointer": proc_pointer,
                "source_text": proc_text,
                "calculation_count": len(calc_records),
                "calculations": calc_records,
            }
        )

    index_data = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": source.strategy_id,
        "source_strategy_path": str(strategy_path),
        "computational_json_pointer": source.pointer,
        "translator_policy": {
            "role": "translate_only",
            "feasibility_judgment": "not_performed",
            "calculation_execution": "not_performed",
            "proxy_substitution": "not_performed",
        },
        "procedure_count": len(index_records),
        "procedures": index_records,
    }
    write_json(out / "recipe_index.json", index_data)
    write_text(out / "recipe_index.md", render_index_md(index_data))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
