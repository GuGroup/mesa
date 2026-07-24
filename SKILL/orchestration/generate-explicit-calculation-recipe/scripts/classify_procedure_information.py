#!/usr/bin/env python3
import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from generate_explicit_recipe import load_json
from map_strategy_to_procedures import load_env, response_text


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True, type=Path)
    parser.add_argument("--recipe-root", required=True, type=Path)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.6-sol"))
    return parser.parse_args()


def resolve(data, pointer):
    value = data
    for token in pointer.removeprefix("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def procedure_inputs(data, recipe_root):
    result = []
    for folder in sorted(path for path in recipe_root.glob("P[0-9][0-9][0-9]") if path.is_dir()):
        source_text = load_json(folder / "procedure.json").get("source_text")
        pointers = load_json(folder / "mapping.json").get("source_json_pointers")
        if not isinstance(source_text, str) or not isinstance(pointers, list) or not pointers:
            raise SystemExit(f"invalid procedure or mapping: {folder}")
        if len(pointers) != len(set(pointers)) or not all(isinstance(pointer, str) for pointer in pointers):
            raise SystemExit(f"invalid source pointers: {folder}")
        sources = [
            {
                "source_id": f"M{index:03d}",
                "source_json_pointer": pointer,
                "value": resolve(data, pointer),
            }
            for index, pointer in enumerate(pointers, 1)
        ]
        result.append({"folder": folder, "source_text": source_text, "sources": sources})
    if not result:
        raise SystemExit("no procedure folders found")
    return result


def classify_with_llm(item, model):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required")
    prompt = {
        "task": "Dissect the procedure into explicit C tasks and classify its mapped information.",
        "rules": [
            "Return p_shared and an ordered list of c_tasks.",
            "Each C task must contain task and source_ids.",
            "Write task as a concise instruction derived only from source_text and mapped_sources.",
            "Split independently realizable outputs and keep components of one aggregate output together.",
            "Use p_shared only for information that applies to every C task.",
            "Assign other information to every C task it directly informs.",
            "Source IDs may be reused across C tasks.",
            "Classify every source ID.",
            "Do not resolve missing information, judge feasibility, or invent information.",
            "Return JSON only.",
        ],
        "output_shape": {
            "p_shared": ["source IDs"],
            "c_tasks": [{"task": "explicit C-task instruction", "source_ids": ["source IDs"]}],
        },
        "source_text": item["source_text"],
        "mapped_sources": item["sources"],
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


def polish(classification, sources):
    if not isinstance(classification, dict) or set(classification) != {"p_shared", "c_tasks"}:
        raise SystemExit("LLM classification must contain p_shared and c_tasks")
    shared = classification["p_shared"]
    tasks = classification["c_tasks"]
    if not isinstance(shared, list) or not all(isinstance(source_id, str) for source_id in shared):
        raise SystemExit("p_shared must be a list of source IDs")
    if not isinstance(tasks, list) or not tasks:
        raise SystemExit("c_tasks must be a non-empty list")
    order = {source["source_id"]: index for index, source in enumerate(sources)}
    known = set(order)
    shared_set = set(shared)
    polished_tasks = []
    task_names = set()
    task_sets = []
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {"task", "source_ids"}:
            raise SystemExit("each C task must contain task and source_ids")
        task_text = task["task"].strip() if isinstance(task["task"], str) else ""
        source_ids = task["source_ids"]
        if not task_text or task_text in task_names:
            raise SystemExit("C-task instructions must be non-empty and unique")
        if not isinstance(source_ids, list) or not all(isinstance(source_id, str) for source_id in source_ids):
            raise SystemExit("C-task source_ids must be a list of source IDs")
        task_names.add(task_text)
        task_sets.append(set(source_ids))
        polished_tasks.append({"task": task_text, "source_ids": source_ids})
    used = shared_set | set().union(*task_sets)
    if used - known:
        raise SystemExit(f"unknown source IDs: {sorted(used - known)}")
    task_sets = [task_set - shared_set for task_set in task_sets]
    used = shared_set | set().union(*task_sets)
    if used != known:
        raise SystemExit(f"unclassified source IDs: {sorted(known - used)}")
    for task, task_set in zip(polished_tasks, task_sets):
        task["source_ids"] = sorted(task_set, key=order.get)
    return sorted(shared_set, key=order.get), polished_tasks


def main():
    load_env()
    args = parse_args()
    data = load_json(args.strategy)
    items = procedure_inputs(data, args.recipe_root)
    if (args.recipe_root / "recipe_index.json").exists() or any(
        (item["folder"] / "calculations").exists() for item in items
    ):
        raise SystemExit("classified recipes already exist")
    classified = [
        (item, *polish(classify_with_llm(item, args.model), item["sources"]))
        for item in items
    ]
    procedures = []
    for item, shared_ids, tasks in classified:
        procedure_id = item["folder"].name
        sources = {source["source_id"]: source for source in item["sources"]}
        shared = {
            sources[source_id]["source_json_pointer"]: sources[source_id]["value"]
            for source_id in shared_ids
        }
        calculations = item["folder"] / "calculations"
        calculations.mkdir()
        calculation_records = []
        for index, task in enumerate(tasks, 1):
            calculation_id = f"C{index:03d}"
            folder = calculations / calculation_id
            folder.mkdir()
            specific = {
                sources[source_id]["source_json_pointer"]: sources[source_id]["value"]
                for source_id in task["source_ids"]
            }
            (folder / "recipe.json").write_text(
                json.dumps(
                    {
                        "procedure_id": procedure_id,
                        "calculation_id": calculation_id,
                        "source_text": item["source_text"],
                        "c_task": task["task"],
                        "p_shared": shared,
                        "c_specific": specific,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            calculation_records.append({
                "calculation_id": calculation_id,
                "folder": str(folder.relative_to(args.recipe_root)),
            })
        procedures.append({
            "procedure_id": procedure_id,
            "source_text": item["source_text"],
            "calculations": calculation_records,
        })
    strategy = data.get("selected_strategy", data)
    (args.recipe_root / "recipe_index.json").write_text(
        json.dumps(
            {
                "strategy_id": strategy.get("strategy_id", "") if isinstance(strategy, dict) else "",
                "procedures": procedures,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(args.recipe_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
