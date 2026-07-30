#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def load_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("strategy must be a JSON object")
    return data


def find_computational(data):
    for root in (data.get("selected_strategy"), data):
        if not isinstance(root, dict):
            continue
        for key in ("experiment", "experimental"):
            block = root.get(key)
            if isinstance(block, dict) and isinstance(block.get("computational"), dict):
                return block["computational"]
        if isinstance(root.get("computational"), dict):
            return root["computational"]
        if isinstance(root.get("procedures"), list):
            return root
    raise SystemExit("computational procedures not found")


def strategy_id(data):
    root = data.get("selected_strategy", data)
    return root.get("strategy_id") if isinstance(root, dict) else None


def attach_next_run(data, path):
    if path is None:
        return data
    classification = load_json(path)
    if classification.get("schema_version") != "1.0":
        raise SystemExit("next-run artifact schema_version must be 1.0")
    next_run = classification.get("next_run")
    if not isinstance(next_run, dict):
        raise SystemExit("next-run artifact must contain a non-null next_run object")
    if set(next_run) != {"mode", "target_strategy_id", "input_sources", "report"}:
        raise SystemExit("invalid next_run keys")
    mode = next_run.get("mode")
    if mode not in {"extend_strategy", "prerequisite", "replace_strategy"}:
        raise SystemExit("invalid next_run mode")
    if classification.get("classification") != mode:
        raise SystemExit("next_run mode does not match classification")
    target = next_run.get("target_strategy_id")
    if mode in {"extend_strategy", "prerequisite"}:
        if not isinstance(target, str) or target != strategy_id(data):
            raise SystemExit("next_run target does not match strategy")
    elif target is not None:
        raise SystemExit("replace_strategy target_strategy_id must be null")
    input_sources = next_run.get("input_sources")
    if (
        not isinstance(input_sources, list)
        or not input_sources
        or len(input_sources) != len(set(input_sources))
        or not all(isinstance(item, str) and item.strip() for item in input_sources)
    ):
        raise SystemExit("next_run input_sources must be non-empty unique strings")
    report = next_run.get("report")
    if (
        not isinstance(report, list)
        or not 1 <= len(report) <= 6
        or not all(
            isinstance(item, str)
            and item.strip()
            and len(re.findall(r"[.!?]+(?=\s|$)", item.strip())) == 1
            for item in report
        )
    ):
        raise SystemExit("next_run report must contain one to six one-sentence items")
    if "next_run" in data:
        raise SystemExit("strategy already contains next_run")
    merged = dict(data)
    merged["next_run"] = next_run
    return merged


def main():
    args = parse_args()
    procedures = find_computational(load_json(args.strategy)).get("procedures")
    if not isinstance(procedures, list) or not procedures or not all(isinstance(text, str) for text in procedures):
        raise SystemExit("procedures must be a non-empty list of strings")

    args.out.mkdir(parents=True)
    for number, source_text in enumerate(procedures, 1):
        folder = args.out / f"P{number:03d}"
        folder.mkdir()
        (folder / "procedure.json").write_text(
            json.dumps({"source_text": source_text}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
