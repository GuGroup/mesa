#!/usr/bin/env python3
import argparse
import json
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
