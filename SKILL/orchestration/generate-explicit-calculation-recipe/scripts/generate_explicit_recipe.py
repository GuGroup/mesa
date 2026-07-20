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
    "status", "blocked", "unsupported", "executable", "feasible",
    "requires_repair", "reason", "why_cannot_be_done",
}

ROLE_TEMPLATES: dict[str, dict[str, Any]] = json.loads(
    Path(__file__).with_name("recipe_role_templates.json").read_text(encoding="utf-8")
)
CANONICAL_RECIPE_ROLES = set(ROLE_TEMPLATES)


@dataclass(frozen=True)
class ComputationalSource:
    strategy: dict[str, Any]
    computational: dict[str, Any]
    pointer: str
    strategy_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate a computational strategy into explicit calculation recipes.")
    parser.add_argument("--strategy", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))
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
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def find_computational_section(data: dict[str, Any]) -> ComputationalSource:
    roots = [(data.get("selected_strategy"), "/selected_strategy"), (data, "")]
    for root, prefix in roots:
        if not isinstance(root, dict):
            continue
        for key in ("experiment", "experimental"):
            block = root.get(key)
            if isinstance(block, dict) and isinstance(block.get("computational"), dict):
                pointer = f"{prefix}/{key}/computational" if prefix else f"/{key}/computational"
                return ComputationalSource(root, block["computational"], pointer, str(root.get("strategy_id", "")))
        if isinstance(root.get("computational"), dict):
            pointer = f"{prefix}/computational" if prefix else "/computational"
            return ComputationalSource(root, root["computational"], pointer, str(root.get("strategy_id", "")))
    raise SystemExit("could not find a supported computational section in strategy artifact")


def slugify(text: str, max_length: int = 72) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return (re.sub(r"_+", "_", slug).strip("_") or "item")[:max_length].strip("_") or "item"


def write_json(path: Path, data: dict[str, Any], *, validate: bool = False) -> None:
    if validate:
        assert_no_decision_fields(data, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def assert_no_decision_fields(value: Any, path: Path) -> None:
    if isinstance(value, dict):
        overlap = FORBIDDEN_DECISION_FIELDS.intersection(value)
        if overlap:
            raise SystemExit(f"forbidden decision fields {sorted(overlap)} would be written to {path}")
        for child in value.values():
            assert_no_decision_fields(child, path)
    elif isinstance(value, list):
        for child in value:
            assert_no_decision_fields(child, path)


def source_context(computational: dict[str, Any]) -> dict[str, Any]:
    keys = ("models", "methods", "dft_details", "computational_tests_to_run", "computational_benchmark_comparisons")
    return {key: computational[key] for key in keys if key in computational}


def list_strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def split_items(text: str, *, semicolon_first: bool = False) -> list[str]:
    separator = ";" if semicolon_first and ";" in text else ","
    normalized = re.sub(r",?\s+and\s+", f"{separator} ", text, flags=re.I)
    return [item.strip(" .") for item in normalized.split(separator) if item.strip(" .")]


def extract_after_label(text: str, labels: tuple[str, ...]) -> list[str]:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"\b(?:{label_pattern})\b\s*:\s*(.+)$", text, flags=re.I)
    return split_items(match.group(1), semicolon_first=True) if match else []


def extract_model_items(text: str, computational: dict[str, Any]) -> list[str]:
    match = re.search(
        r"\b(?:build|construct|create|generate|prepare)\b\s+(?:the\s+)?(.+?)\s+"
        r"(?:models?(?:\s+set)?|structures?|slabs?|surfaces?|clusters?|cells?)"
        r"(?=\s+(?:using|with|under|for)\b|[.;]|$)",
        text,
        flags=re.I,
    )
    if match:
        items = split_items(re.sub(r"^(?:clean|relaxed|matched)\s+", "", match.group(1), flags=re.I))
        if items:
            return items
    return list_strings(computational.get("models")) or ["source-defined model"]


def extract_state_items(text: str) -> list[str]:
    items = extract_after_label(text, ("states", "state sequence", "sequence", "endpoints", "intermediates"))
    if items:
        return items
    if re.search(r"free[- ]energy", text, flags=re.I) and ":" in text:
        return split_items(text.split(":", 1)[1], semicolon_first=True)
    return []


def extract_descriptor_items(text: str) -> list[str]:
    return extract_after_label(text, ("descriptors", "descriptor", "metrics", "properties"))


def extract_conditions(text: str, computational: dict[str, Any]) -> list[str]:
    context = json.dumps(computational.get("dft_details", {}), ensure_ascii=False)
    haystack = f"{text} {context}"
    patterns = (
        r"\bpH\s*(?:=|of)?\s*-?\d+(?:\.\d+)?",
        r"(?:\bU\s*=\s*)?[+-]?\d+(?:\.\d+)?\s*V(?:\s*(?:vs\.?|versus)\s*[A-Za-z0-9+_./-]+)?",
        r"\b\d+(?:\.\d+)?\s*K\b",
        r"\b\d+(?:\.\d+)?\s*(?:bar|atm|Pa|kPa)\b",
    )
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, haystack, flags=re.I):
            value = " ".join(match.group(0).split()).rstrip(".,;:")
            if value not in found:
                found.append(value)
    return found


def deterministic_roles(source_text: str) -> list[str]:
    text = " ".join(source_text.lower().split())
    roles: list[str] = []

    def add(role: str, condition: bool) -> None:
        if condition and role not in roles:
            roles.append(role)

    build = bool(re.search(r"\b(build|construct|create|generate|prepare)\b", text))
    structure = bool(re.search(r"\b(model|structure|slab|surface|cluster|molecule|bulk|cell|interface)s?\b", text))
    state_signal = bool(re.search(r"\b(adsorbate|adsorbed|adsorption|intermediate|endpoint|state)s?\b", text))
    relax = bool(re.search(r"\b(relax|optimi[sz]e|minimi[sz]e)\b", text))
    placement = bool(re.search(r"\b(place|position|adsorb)\b", text)) and bool(re.search(r"\b(on|site|surface|ensemble)\b", text))

    add("artifact_import", bool(re.search(r"\b(import|reuse|load|collect)\b", text)) and bool(re.search(r"\b(artifact|record|result|control|baseline|structure|data)s?\b", text)))
    add("structure_model_build", build and structure and not re.search(r"\b(diagram|profile|plot)\b", text))
    figure_signal = bool(re.search(r"\b(diagrams?|profiles?|plots?|reaction coordinates?)\b", text))
    add("adsorbate_structure_build", placement or (build and state_signal and not figure_signal))
    add("adsorbate_relaxation_matrix", relax and state_signal)
    add("clean_structure_relaxation", relax and bool(re.search(r"\b(clean|bare|unadsorbed)\b", text)))
    add("single_point_energy_calculation", bool(re.search(r"\b(single[- ]point|static)\b", text)) and bool(re.search(r"\b(energy|calculation)s?\b", text)))
    add("vibrational_analysis", bool(re.search(r"\b(vibration|vibrational|frequency|phonon|zero[- ]point|zpe)s?\b", text)))
    add("reaction_pathway_search", bool(re.search(r"\b(neb|transition state|reaction path|minimum energy path|activation barrier)\b", text)))
    add("molecular_dynamics", bool(re.search(r"\b(aimd|molecular dynamics|ab initio dynamics)\b", text)))
    solvation = bool(re.search(
        r"\bsolvat\w*\s+(?:effect|energy|analysis|model)s?\b"
        r"|\bsolvent\s+(?:effect|correction|model)s?\b"
        r"|\b(?:implicit|explicit)\s+(?:solvent|water)\b",
        text,
    ))
    add("solvation_analysis", solvation)

    pdos = bool(re.search(r"\bpdos\b|projected\s+(?:density of states|dos)", text))
    dos = bool(re.search(r"\bdos\b|density of states", text))
    add("projected_dos_analysis", pdos)
    add("density_of_states_analysis", dos and not pdos)
    add("charge_transfer_analysis", bool(re.search(r"\b(charge transfer|charge[- ]density|bader|population analysis|electron redistribution)\b", text)))

    free_energy = bool(re.search(r"\b(free[- ]energy|gibbs energy)\b", text))
    add("free_energy_state_definition", bool(extract_state_items(source_text)))
    add("free_energy_diagram_assembly", free_energy and bool(re.search(r"\b(diagrams?|profiles?|sequence|reaction coordinates?)\b", text)))
    electrochemical = bool(re.search(r"\b(ph|potential|rhe|she|electrochemical|proton|electron)\b", text))
    add("electrochemical_free_energy_bookkeeping", free_energy and electrochemical)
    add("potential_shift_analysis", bool(re.search(r"\b(potential sweep|potential dependence|potential[- ]dependent|shift.+potential|potential grid)\b", text)))

    descriptor_action = bool(re.search(r"\b(calculate|compute|extract|compare|rank|classify|assign|record|evaluate|analy[sz]e|test|reject|screen|filter)\b", text))
    descriptor_object = bool(re.search(
        r"\b(descriptor|metric|ranking|limiting step|energy span|identity|endpoint|mechanism|distance|criterion|flag|trend|balance|control|baseline)s?\b"
        r"|\buphill\b.*\b(step|span)\b",
        text,
    ))
    add("descriptor_calculation", bool(extract_descriptor_items(source_text)) or (descriptor_action and descriptor_object))
    add("stability_analysis", bool(re.search(r"\b(stability|stable|formation energy|decomposition|reconstruction|segregation|dissolution)\b", text)) and descriptor_action)
    add("benchmark_constraint_comparison", bool(re.search(r"\b(benchmark|experimental constraint|reference data|validation target)\b", text)) or ("compare" in text and bool(re.search(r"\b(control|baseline|reference)\b", text))))
    return roles


def response_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    return "\n".join(
        content["text"]
        for item in response.get("output", []) if isinstance(item, dict)
        for content in item.get("content", [])
        if isinstance(content, dict) and isinstance(content.get("text"), str)
    )


def parse_role_decisions(text: str, source_text: str) -> list[dict[str, str]]:
    payload = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()))
    raw = payload.get("roles") if isinstance(payload, dict) else None
    if not isinstance(raw, list) or not raw:
        raise ValueError("LLM role output must contain a non-empty roles list")
    normalized_source = " ".join(source_text.split()).casefold()
    decisions: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each LLM role decision must be an object")
        role = str(item.get("recipe_role", "")).strip()
        phrase = " ".join(str(item.get("source_phrase", "")).split())
        if role not in CANONICAL_RECIPE_ROLES:
            raise ValueError(f"LLM returned unknown recipe_role: {role!r}")
        if not phrase or phrase.casefold() not in normalized_source:
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
        "task": "Select calculation roles explicitly requested by this computational-chemistry procedure.",
        "allowed_recipe_roles": sorted(CANONICAL_RECIPE_ROLES),
        "rules": [
            "Return only roles supported by the procedure.",
            "Copy an exact source_phrase from the procedure for each role.",
            "Do not infer catalyst, reaction, conditions, intermediates, or methods absent from the source.",
            "Do not judge feasibility or substitute calculations.",
            'Return JSON only as {"roles":[{"recipe_role":"...","source_phrase":"..."}]}',
        ],
        "procedure": source_text,
        "context": source_context(computational),
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps({"model": model, "input": [{"role": "user", "content": [{"type": "input_text", "text": json.dumps(prompt)}]}]}).encode(),
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


def make_recipe(
    *, strategy_id: str, procedure_id: str, calculation_id: str, source_text: str,
    pointer: str, role: str, item: str | None = None, conditions: list[str] | None = None,
    source_phrase: str | None = None,
) -> dict[str, Any]:
    template = ROLE_TEMPLATES[role]
    title = template["title"]
    if item:
        if role == "structure_model_build":
            title = f"Build model: {item}"
        elif role == "free_energy_state_definition":
            title = f"Define free-energy state: {item}"
        elif role == "descriptor_calculation":
            title = f"Calculate descriptor: {item}"
    source_terms: dict[str, Any] = {}
    inputs = list(template["inputs"])
    if item:
        source_terms["item"] = item
        inputs.append(item)
    if conditions:
        source_terms["conditions"] = conditions
        inputs.extend(conditions)
    if source_phrase:
        source_terms["source_phrase"] = source_phrase
        inputs.append(source_phrase)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "procedure_id": procedure_id,
        "calculation_id": calculation_id,
        "source_json_pointer": pointer,
        "source_procedure_text": source_text,
        "recipe_role": role,
        "calculation_title": title,
        "required_prior_artifacts": list(template["prior"]),
        "required_inputs": list(dict.fromkeys(inputs)),
        "operations": list(template["operations"]),
        "method_intent": list(template["method"]),
        "output_artifacts": list(template["outputs"]),
        "source_terms": source_terms,
        "notes": [],
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
    roles = deterministic_roles(source_text)
    llm_phrases: dict[str, str] = {}
    if not roles:
        classifier = role_classifier or (
            lambda text, context: classify_roles_with_llm(text, context, os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))
        )
        decisions = classifier(source_text, computational)
        roles = [decision["recipe_role"] for decision in decisions]
        llm_phrases = {decision["recipe_role"]: decision["source_phrase"] for decision in decisions}

    conditions = extract_conditions(source_text, computational)
    model_items = extract_model_items(source_text, computational) if "structure_model_build" in roles else []
    state_items = extract_state_items(source_text)
    descriptor_items = extract_descriptor_items(source_text)
    recipes: list[dict[str, Any]] = []

    for role in roles:
        items: list[str | None] = [None]
        if role == "structure_model_build":
            items = model_items
        elif role == "free_energy_state_definition" and state_items:
            items = state_items
        elif role == "descriptor_calculation" and descriptor_items:
            items = descriptor_items
        for item in items:
            recipes.append(make_recipe(
                strategy_id=strategy_id,
                procedure_id=procedure_id,
                calculation_id=f"C{len(recipes) + 1:03d}",
                source_text=source_text,
                pointer=pointer,
                role=role,
                item=item,
                conditions=conditions if role in {"electrochemical_free_energy_bookkeeping", "potential_shift_analysis"} else None,
                source_phrase=llm_phrases.get(role),
            ))
    return recipes


def render_recipe_md(data: dict[str, Any]) -> str:
    lines = [
        f"# {data['calculation_id']} {data['calculation_title']}", "",
        f"- Procedure: `{data['procedure_id']}`", f"- Role: `{data['recipe_role']}`",
        f"- Source: `{data['source_json_pointer']}`",
    ]
    if data.get("source_phrase"):
        lines.append(f"- Source phrase: {data['source_phrase']}")
    lines.extend(["", "## Source Procedure", "", data["source_procedure_text"]])
    for title, key in (
        ("Required Prior Artifacts", "required_prior_artifacts"),
        ("Required Inputs", "required_inputs"),
        ("Operations", "operations"),
        ("Method Intent", "method_intent"),
        ("Output Artifacts", "output_artifacts"),
    ):
        lines.extend(["", f"## {title}", "", *[f"- {item}" for item in data[key]]])
    return "\n".join(lines) + "\n"


def render_procedure_map(data: dict[str, Any], calculations: list[dict[str, Any]]) -> str:
    lines = [f"# {data['procedure_id']} Procedure Map", "", "## Source Procedure", "", data["source_text"], "", "## Generated Calculation Recipes", ""]
    lines.extend(f"- `{calc['calculation_id']}` {calc['calculation_title']}" for calc in calculations)
    return "\n".join(lines) + "\n"


def render_index_md(data: dict[str, Any]) -> str:
    lines = [
        "# Explicit Calculation Recipe Index", "", f"- Strategy ID: `{data['strategy_id']}`",
        f"- Computational source: `{data['computational_json_pointer']}`",
        f"- Procedure count: {data['procedure_count']}", "",
        "This artifact translates the strategy computational section into recipe folders. It does not evaluate feasibility.",
        "", "## Procedures", "",
    ]
    lines.extend(
        f"- `{procedure['procedure_id']}` {procedure['source_text']} ({procedure['calculation_count']} calculation recipes)"
        for procedure in data["procedures"]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    load_env()
    args = parse_args()
    strategy_path, out = args.strategy.resolve(), args.out.resolve()
    source = find_computational_section(load_json(strategy_path))
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

    for number, source_text in enumerate(procedures, start=1):
        procedure_id = f"P{number:03d}"
        pointer = f"{source.pointer}/procedures/{number - 1}"
        procedure_folder = out / procedure_id
        calculations = build_recipes_for_procedure(
            source.strategy_id, procedure_id, pointer, source_text, source.computational,
            role_classifier=lambda text, block: classify_roles_with_llm(text, block, args.model),
        )
        calculation_records: list[dict[str, str]] = []
        for calculation in calculations:
            folder = procedure_folder / "calculations" / f"{calculation['calculation_id']}_{slugify(calculation['calculation_title'])}"
            write_json(folder / "recipe.json", calculation, validate=True)
            write_text(folder / "recipe.md", render_recipe_md(calculation))
            record = {
                "calculation_id": calculation["calculation_id"],
                "folder": str(folder.relative_to(out)),
                "calculation_title": calculation["calculation_title"],
                "recipe_role": calculation["recipe_role"],
            }
            if calculation.get("source_phrase"):
                record["source_phrase"] = calculation["source_phrase"]
            calculation_records.append(record)
        procedure_data = {
            "schema_version": SCHEMA_VERSION,
            "strategy_id": source.strategy_id,
            "procedure_id": procedure_id,
            "source_json_pointer": pointer,
            "source_text": source_text,
            "source_context": context,
            "calculation_folders": calculation_records,
        }
        write_json(procedure_folder / "procedure.json", procedure_data)
        write_text(procedure_folder / "procedure_map.md", render_procedure_map(procedure_data, calculations))
        index_records.append({
            "procedure_id": procedure_id,
            "folder": procedure_id,
            "source_json_pointer": pointer,
            "source_text": source_text,
            "calculation_count": len(calculation_records),
            "calculations": calculation_records,
        })

    index = {
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
    write_json(out / "recipe_index.json", index)
    write_text(out / "recipe_index.md", render_index_md(index))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
