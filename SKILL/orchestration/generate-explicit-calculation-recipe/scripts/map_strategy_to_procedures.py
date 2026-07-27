#!/usr/bin/env python3
import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from generate_explicit_recipe import find_computational, load_json


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True, type=Path)
    parser.add_argument("--recipe-root", required=True, type=Path)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.6-sol"))
    return parser.parse_args()


def load_env():
    for path in (Path(".env"), Path("DEPENDENCY/.env")):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def source_catalog(data):
    values = []

    def walk(value, pointer):
        if isinstance(value, dict):
            for key, child in value.items():
                if key != "procedures":
                    token = str(key).replace("~", "~0").replace("/", "~1")
                    walk(child, f"{pointer}/{token}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{pointer}/{index}")
        else:
            values.append({
                "source_id": f"S{len(values) + 1:04d}",
                "source_json_pointer": pointer,
                "value": value,
            })

    strategy = data["selected_strategy"] if isinstance(data.get("selected_strategy"), dict) else data
    prefix = "/selected_strategy" if strategy is not data else ""
    for key in ("experiment", "results"):
        if key in strategy:
            walk(strategy[key], f"{prefix}/{key}")
    return values


def procedures(data, recipe_root):
    source = find_computational(data).get("procedures")
    if not isinstance(source, list) or not source or not all(isinstance(text, str) for text in source):
        raise SystemExit("procedures must be a non-empty list of strings")
    expected = [f"P{index:03d}" for index in range(1, len(source) + 1)]
    actual = sorted(path.name for path in recipe_root.glob("P[0-9][0-9][0-9]") if path.is_dir())
    if actual != expected:
        raise SystemExit("procedure folders do not match the strategy")
    result = []
    for procedure_id, source_text in zip(expected, source):
        payload = load_json(recipe_root / procedure_id / "procedure.json")
        if payload != {"source_text": source_text}:
            raise SystemExit(f"{procedure_id}/procedure.json does not match the strategy")
        result.append({"procedure_id": procedure_id, "source_text": source_text})
    return result


def response_text(response):
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    return "\n".join(
        content["text"]
        for item in response.get("output", []) if isinstance(item, dict)
        for content in item.get("content", [])
        if isinstance(content, dict) and isinstance(content.get("text"), str)
    )


def map_with_llm(procedure_list, catalog, model):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required")
    output_shape = {item["procedure_id"]: ["source IDs"] for item in procedure_list}
    prompt = {
        "task": "Map sufficient strategy information to each procedure.",
        "rules": [
            "Return one JSON object with exactly the procedure IDs shown.",
            "Each value must be a list of source_id values from the catalog.",
            "Reuse a source ID across procedures only when it directly informs each procedure.",
            "Preserve all directly relevant inputs, methods, settings, conditions, constraints, tests, comparisons, and intended outputs.",
            "Do not judge feasibility, priority, or execution and do not invent information.",
            "Return JSON only.",
        ],
        "output_shape": output_shape,
        "procedures": procedure_list,
        "source_catalog": catalog,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps({"model": model, "input": json.dumps(prompt, ensure_ascii=False)}).encode(),
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
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", response_text(result).strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"LLM returned invalid JSON: {exc}") from exc


def polish(mapping, procedure_list, catalog):
    procedure_ids = [item["procedure_id"] for item in procedure_list]
    if not isinstance(mapping, dict) or set(mapping) != set(procedure_ids):
        raise SystemExit("LLM mapping must contain exactly the procedure IDs")
    sources = {item["source_id"]: item for item in catalog}
    order = {source_id: index for index, source_id in enumerate(sources)}
    result = {}
    for procedure_id in procedure_ids:
        source_ids = mapping[procedure_id]
        if not isinstance(source_ids, list) or not all(isinstance(source_id, str) for source_id in source_ids):
            raise SystemExit(f"{procedure_id} mapping must be a list of source IDs")
        unknown = set(source_ids) - set(sources)
        if unknown:
            raise SystemExit(f"{procedure_id} contains unknown source IDs: {sorted(unknown)}")
        result[procedure_id] = [
            sources[source_id]["source_json_pointer"]
            for source_id in sorted(set(source_ids), key=order.get)
        ]
    return result


def main():
    load_env()
    args = parse_args()
    data = load_json(args.strategy)
    procedure_list = procedures(data, args.recipe_root)
    catalog = source_catalog(data)
    mapping = polish(map_with_llm(procedure_list, catalog, args.model), procedure_list, catalog)
    for procedure_id, pointers in mapping.items():
        path = args.recipe_root / procedure_id / "mapping.json"
        path.write_text(json.dumps({"source_json_pointers": pointers}, indent=2) + "\n", encoding="utf-8")
    print(args.recipe_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
