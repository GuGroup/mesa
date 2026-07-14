#!/usr/bin/env python3
"""Check an adsorbate against the vendored AdsorbDiff adsorbate database."""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPO = SKILL_DIR / "assets" / "AdsorbDiff"
DEFAULT_DB = DEFAULT_REPO / "adsorbdiff" / "placement" / "pkls" / "adsorbates.pkl"
TASK_ID = "place-adsorbates-with-adsorbdiff.adsorbate-check"


def load_adsorbate_db(repo: Path, db_path: Path) -> dict[int, tuple[Any, ...]]:
    sys.path.insert(0, str(repo))
    with db_path.open("rb") as handle:
        data = pickle.load(handle)
    if not isinstance(data, dict):
        raise ValueError("adsorbates.pkl did not contain a dictionary")
    return data


def record_to_summary(index: int, record: tuple[Any, ...]) -> dict[str, Any]:
    atoms = record[0]
    smiles = record[1] if len(record) > 1 else None
    binding_indices = [int(item) for item in record[2]] if len(record) > 2 else []
    summary = {
        "id": int(index),
        "smiles": smiles,
        "binding_indices": binding_indices,
        "n_binding_indices": len(binding_indices),
    }
    if hasattr(atoms, "get_chemical_formula"):
        summary["formula"] = atoms.get_chemical_formula()
    if hasattr(atoms, "get_chemical_symbols"):
        summary["symbols"] = atoms.get_chemical_symbols()
        summary["n_atoms"] = len(summary["symbols"])
    if len(record) > 3:
        summary["reaction_string"] = record[3]
    return summary


def select_adsorbate(
    records: dict[int, tuple[Any, ...]],
    adsorbate_id: int | None,
    smiles: str | None,
    formula: str | None,
    allow_ambiguous_select: bool,
) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    messages: list[str] = []
    if adsorbate_id is not None:
        if adsorbate_id not in records:
            return "failure", None, [], [f"adsorbate id was not found: {adsorbate_id}"]
        return "success", record_to_summary(adsorbate_id, records[adsorbate_id]), [], messages

    summaries = [record_to_summary(index, record) for index, record in sorted(records.items())]
    matches: list[dict[str, Any]] = []
    if smiles:
        matches = [item for item in summaries if item.get("smiles") == smiles]
    elif formula:
        matches = [item for item in summaries if item.get("formula") == formula]
    else:
        return "summary", None, summaries, messages

    if not matches:
        return "failure", None, [], [f"adsorbate was not found: {smiles or formula}"]
    if len(matches) == 1:
        return "success", matches[0], matches, messages
    if allow_ambiguous_select:
        selected = sorted(matches, key=lambda item: (item.get("n_atoms", 10**9), item["id"]))[0]
        messages.append(
            f"Multiple adsorbates matched; selected id {selected['id']} by smallest n_atoms then lowest id."
        )
        return "success", selected, matches, messages
    return "ambiguous", None, matches, [f"{len(matches)} adsorbates matched; provide id or SMILES."]


def check_adsorbate(
    repo: Path = DEFAULT_REPO,
    db_path: Path = DEFAULT_DB,
    adsorbate_id: int | None = None,
    smiles: str | None = None,
    formula: str | None = None,
    allow_ambiguous_select: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    messages: list[str] = []
    selected = None
    matches: list[dict[str, Any]] = []
    total_adsorbates = None
    try:
        if not db_path.exists():
            raise FileNotFoundError(f"adsorbate database not found: {db_path}")
        records = load_adsorbate_db(repo, db_path)
        total_adsorbates = len(records)
        status, selected, matches, select_messages = select_adsorbate(
            records,
            adsorbate_id=adsorbate_id,
            smiles=smiles,
            formula=formula,
            allow_ambiguous_select=allow_ambiguous_select,
        )
        messages.extend(select_messages)
        if status == "failure":
            errors.extend({"type": "AdsorbateNotFound", "message": item} for item in select_messages)
        elif status == "summary":
            matches = matches[: limit or 20]
        elif status == "ambiguous":
            errors.extend({"type": "AmbiguousAdsorbate", "message": item} for item in select_messages)
            matches = matches[: limit or 20]
    except ModuleNotFoundError as exc:
        status = "failure"
        errors.append(
            {
                "type": "MissingDependency",
                "message": f"Loading adsorbates.pkl requires the AdsorbDiff environment dependency: {exc.name}",
            }
        )
    except Exception as exc:  # noqa: BLE001
        status = "failure"
        errors.append({"type": type(exc).__name__, "message": str(exc)})

    return {
        "status": "failure" if errors else status,
        "task_id": TASK_ID,
        "skill": "adsorbate_checker",
        "data": {
            "repo": str(repo),
            "adsorbate_db": str(db_path),
            "total_adsorbates": total_adsorbates,
            "query": {"id": adsorbate_id, "smiles": smiles, "formula": formula},
            "selected": selected,
            "matches": matches,
        },
        "artifacts": [],
        "messages": messages,
        "errors": errors,
        "provenance": {
            "inputs": [str(db_path)],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "next_action": {
            "recommendation": "fix_adsorbate" if errors else "prepare_placement",
            "reason": "Adsorbate check failed." if errors else "Adsorbate identity is available.",
        },
    }


def self_test() -> int:
    result = check_adsorbate(db_path=DEFAULT_DB, adsorbate_id=None, smiles=None, formula=None, limit=1)
    if DEFAULT_DB.exists() and result["status"] in {"summary", "failure"}:
        print("self-test passed")
        return 0
    print(json.dumps(result, indent=2))
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--adsorbate-id", type=int)
    parser.add_argument("--smiles")
    parser.add_argument("--formula")
    parser.add_argument("--allow-ambiguous-select", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    result = check_adsorbate(
        repo=args.repo.resolve(),
        db_path=args.db_path.resolve(),
        adsorbate_id=args.adsorbate_id,
        smiles=args.smiles,
        formula=args.formula,
        allow_ambiguous_select=args.allow_ambiguous_select,
        limit=args.limit,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
