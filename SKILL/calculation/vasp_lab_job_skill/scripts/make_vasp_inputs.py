#!/usr/bin/env python3
"""Generate lab-standard VASP input directories and optionally submit with SGE qsub.

Examples:
  python scripts/make_vasp_inputs.py --calc-type gas --poscar POSCAR --outdir gas/NH3 --submit
  python scripts/make_vasp_inputs.py --calc-type bulk --poscar POSCAR --outdir bulk/opt --submit
  python scripts/make_vasp_inputs.py --calc-type slab-kconv --poscar POSCAR_slab --project-root . --submit
  python scripts/make_vasp_inputs.py --calc-type slab-encut --poscar POSCAR_slab --selected-settings slab_convergence.yml --submit
  python scripts/make_vasp_inputs.py --calc-type ads --poscar POSCAR_NH3 --outdir ads/NH3_site01 --selected-settings slab_convergence.yml --submit
  python scripts/make_vasp_inputs.py --calc-type freq --poscar ads/NH3_site01/CONTCAR --outdir freq/NH3_site01 --selected-settings slab_convergence.yml --mobile-indices 97-104 --submit
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from vasp_lab_common import (
    SkillError,
    choose_submit_script,
    copy_submit_script,
    ensure_vasp_pp_path,
    get_vasp_params,
    load_defaults,
    load_yaml,
    parse_indices,
    parse_int_list,
    parse_overrides,
    setups_from_defaults,
    submit_with_qsub,
    write_manifest,
    write_yaml,
)

CALC_TYPES = ["gas", "bulk", "slab-kconv", "slab-encut", "slab-final", "ads", "oxide-ads", "freq"]


def selected_settings(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    data = load_yaml(path)
    return data.get("slab_convergence", data)


def kpts_from_settings(settings: dict[str, Any]) -> list[int] | None:
    value = settings.get("selected_kpts") or settings.get("kpts")
    if value is None:
        return None
    return [int(x) for x in value]


def encut_from_settings(settings: dict[str, Any]) -> int | None:
    value = settings.get("selected_encut") or settings.get("encut")
    return int(value) if value is not None else None


def layer_groups_by_z(atoms: Any, tolerance: float) -> list[list[int]]:
    indexed = sorted(enumerate(atoms.positions[:, 2]), key=lambda item: item[1])
    groups: list[list[int]] = []
    group: list[int] = []
    last_z: float | None = None
    for idx, z in indexed:
        if last_z is None or abs(float(z) - last_z) <= tolerance:
            group.append(idx)
        else:
            groups.append(group)
            group = [idx]
        last_z = float(z)
    if group:
        groups.append(group)
    return groups


def apply_bottom_layer_fix(atoms: Any, n_layers: int, tolerance: float) -> list[int]:
    try:
        from ase.constraints import FixAtoms
    except ModuleNotFoundError as exc:
        raise SkillError("ASE is required for applying atom constraints.") from exc
    groups = layer_groups_by_z(atoms, tolerance=tolerance)
    fixed: list[int] = []
    for group in groups[:n_layers]:
        fixed.extend(group)
    atoms.set_constraint(FixAtoms(indices=sorted(fixed)))
    return sorted(fixed)


def apply_mobile_indices_for_freq(atoms: Any, mobile_indices: list[int] | None, adsorbate_elements: list[str] | None) -> list[int] | None:
    try:
        from ase.constraints import FixAtoms
    except ModuleNotFoundError as exc:
        raise SkillError("ASE is required for applying atom constraints.") from exc
    if mobile_indices is None and not adsorbate_elements:
        return None
    if mobile_indices is None:
        mobile_set = {i for i, atom in enumerate(atoms) if atom.symbol in set(adsorbate_elements or [])}
    else:
        mobile_set = set(mobile_indices)
    fixed = [i for i in range(len(atoms)) if i not in mobile_set]
    atoms.set_constraint(FixAtoms(indices=fixed))
    return fixed


def apply_magmom_rules(atoms: Any, profile: dict[str, Any]) -> list[float] | None:
    rules = profile.get("magmom_rules") or {}
    if not rules:
        return None
    ordered = rules.get("ordered_counts", {}) or {}
    default_by_element = rules.get("default_by_element", {}) or {}
    seen: dict[str, int] = {}
    magmoms: list[float] = []
    any_rule = False
    for atom in atoms:
        symbol = atom.symbol
        seen[symbol] = seen.get(symbol, 0) + 1
        if symbol in ordered:
            any_rule = True
            spec = ordered[symbol]
            first = spec.get("first", {})
            if seen[symbol] <= int(first.get("count", 0)):
                magmoms.append(float(first.get("value", 0.0)))
            else:
                magmoms.append(float(spec.get("rest", 0.0)))
        elif symbol in default_by_element:
            any_rule = True
            magmoms.append(float(default_by_element[symbol]))
        else:
            magmoms.append(float(default_by_element.get("default", 0.0)))
    if any_rule:
        atoms.set_initial_magnetic_moments(magmoms)
        return magmoms
    return None


def make_one_job(
    *,
    calc_type: str,
    poscar: Path,
    calc_dir: Path,
    kpts: list[int],
    encut: int | None,
    defaults: dict[str, Any],
    profile_name: str | None,
    overrides: dict[str, Any],
    cores: int,
    submit: bool,
    dry_run_submit: bool,
    allow_unverified_profile: bool,
    fix_bottom_layers: int | None,
    layer_tolerance: float,
    mobile_indices_text: str | None,
    adsorbate_elements: list[str] | None,
) -> dict[str, Any]:
    if not poscar.is_file():
        raise SkillError(f"POSCAR/CONTCAR not found: {poscar}")
    try:
        from ase.calculators.vasp import Vasp
        from ase.io import read
    except ModuleNotFoundError as exc:
        raise SkillError("ASE is required for VASP input generation. Install ase or run in the modeling environment.") from exc

    atoms = read(str(poscar))

    fixed_indices: list[int] | None = None
    if fix_bottom_layers:
        fixed_indices = apply_bottom_layer_fix(atoms, fix_bottom_layers, tolerance=layer_tolerance)

    if calc_type == "freq":
        mobile_indices = parse_indices(mobile_indices_text, len(atoms))
        fixed_for_freq = apply_mobile_indices_for_freq(atoms, mobile_indices, adsorbate_elements)
        if fixed_for_freq is not None:
            fixed_indices = fixed_for_freq

    profile_used, profile, params = get_vasp_params(
        defaults,
        calc_type,
        profile_name=profile_name,
        overrides=overrides,
        allow_unverified=allow_unverified_profile,
    )

    if encut is not None:
        params["encut"] = int(encut)
    params["kpts"] = [int(x) for x in kpts]
    params.setdefault("setups", setups_from_defaults(defaults))

    magmoms = apply_magmom_rules(atoms, profile)

    ensure_vasp_pp_path(defaults)
    calc_dir.mkdir(parents=True, exist_ok=True)
    calc = Vasp(directory=str(calc_dir), **params)
    calc.write_input(atoms)

    submit_script = choose_submit_script(defaults, calc_type, kpts, cores)
    copied_submit = copy_submit_script(submit_script, calc_dir)
    submit_result = {"submitted": False, "scheduler_id": None}
    if submit:
        submit_result = submit_with_qsub(copied_submit.name, calc_dir, dry_run=dry_run_submit)

    manifest = {
        "calc_type": calc_type,
        "source_poscar": str(poscar.resolve()),
        "calc_dir": str(calc_dir.resolve()),
        "profile": profile_used,
        "profile_source": profile.get("source", {}),
        "kpts": [int(x) for x in kpts],
        "encut": params.get("encut"),
        "cores": cores,
        "submit_script": copied_submit.name,
        "submitted": submit_result.get("submitted", False),
        "scheduler_id": submit_result.get("scheduler_id"),
        "vasp_parameters": params,
        "fixed_indices_1based": [i + 1 for i in fixed_indices] if fixed_indices is not None else None,
        "magmoms": magmoms,
    }
    if "qsub_output" in submit_result:
        manifest["qsub_output"] = submit_result["qsub_output"]
    write_manifest(calc_dir, manifest)
    return manifest


def infer_outdir(calc_type: str, project_root: Path, kpts: list[int] | None, encut: int | None, poscar: Path) -> Path:
    if calc_type == "gas":
        return project_root / "gas" / poscar.stem.replace("POSCAR_", "")
    if calc_type == "bulk":
        return project_root / "bulk" / "opt"
    if calc_type == "slab-kconv":
        if not kpts:
            raise SkillError("kpts are required to infer slab-kconv output directory")
        return project_root / "slab" / "kconv" / f"k{kpts[0]}{kpts[1]}{kpts[2]}"
    if calc_type == "slab-encut":
        if encut is None:
            raise SkillError("encut is required to infer slab-encut output directory")
        return project_root / "slab" / "encut_conv" / f"encut{encut}"
    if calc_type == "slab-final":
        return project_root / "slab" / "final"
    if calc_type in {"ads", "oxide-ads"}:
        return project_root / "ads" / poscar.stem.replace("POSCAR_", "")
    if calc_type == "freq":
        return project_root / "freq" / poscar.parent.name
    raise SkillError(f"Unknown calc_type: {calc_type}")


def run(args: argparse.Namespace) -> dict[str, Any]:
    defaults = load_defaults(args.parameters_yaml)
    settings = selected_settings(args.selected_settings)
    overrides = parse_overrides(args.set)
    project_root = Path(args.project_root).expanduser().resolve()
    poscar = Path(args.poscar).expanduser().resolve() if args.poscar else None

    cores = args.cores or int(defaults.get("submit", {}).get("default_cores", 64))

    jobs: list[dict[str, Any]] = []

    if args.calc_type == "slab-kconv":
        if poscar is None:
            raise SkillError("--poscar is required for slab-kconv")
        series = args.kpoint_series or defaults.get("convergence", {}).get("kpoint_series", [])
        for k in series:
            kpts = [int(x) for x in k]
            encut = args.encut if args.encut is not None else None
            calc_dir = infer_outdir(args.calc_type, project_root, kpts, encut, poscar)
            jobs.append(make_one_job(
                calc_type=args.calc_type,
                poscar=poscar,
                calc_dir=calc_dir,
                kpts=kpts,
                encut=encut,
                defaults=defaults,
                profile_name=args.profile,
                overrides=overrides,
                cores=cores,
                submit=args.submit,
                dry_run_submit=args.dry_run_submit,
                allow_unverified_profile=args.allow_unverified_profile,
                fix_bottom_layers=args.fix_bottom_layers,
                layer_tolerance=args.layer_tolerance,
                mobile_indices_text=args.mobile_indices,
                adsorbate_elements=args.adsorbate_elements,
            ))
    elif args.calc_type == "slab-encut":
        if poscar is None:
            raise SkillError("--poscar is required for slab-encut")
        kpts = args.kpts or kpts_from_settings(settings)
        if not kpts:
            raise SkillError("slab-encut requires --kpts or --selected-settings with selected_kpts")
        series = args.encut_series or defaults.get("convergence", {}).get("encut_series", [])
        for e in series:
            encut = int(e)
            calc_dir = infer_outdir(args.calc_type, project_root, kpts, encut, poscar)
            jobs.append(make_one_job(
                calc_type=args.calc_type,
                poscar=poscar,
                calc_dir=calc_dir,
                kpts=kpts,
                encut=encut,
                defaults=defaults,
                profile_name=args.profile,
                overrides=overrides,
                cores=cores,
                submit=args.submit,
                dry_run_submit=args.dry_run_submit,
                allow_unverified_profile=args.allow_unverified_profile,
                fix_bottom_layers=args.fix_bottom_layers,
                layer_tolerance=args.layer_tolerance,
                mobile_indices_text=args.mobile_indices,
                adsorbate_elements=args.adsorbate_elements,
            ))
    elif args.scan_poscars:
        for p in sorted(project_root.glob(args.scan_poscars)):
            if p.name == "POSCAR_slab":
                continue
            kpts = args.kpts or kpts_from_settings(settings)
            encut = args.encut if args.encut is not None else encut_from_settings(settings)
            if not kpts:
                # Use profile/default kpts if available, else fail after profile resolution.
                kpts = [1, 1, 1]
            calc_dir = infer_outdir(args.calc_type, project_root, kpts, encut, p)
            jobs.append(make_one_job(
                calc_type=args.calc_type,
                poscar=p.resolve(),
                calc_dir=calc_dir,
                kpts=kpts,
                encut=encut,
                defaults=defaults,
                profile_name=args.profile,
                overrides=overrides,
                cores=cores,
                submit=args.submit,
                dry_run_submit=args.dry_run_submit,
                allow_unverified_profile=args.allow_unverified_profile,
                fix_bottom_layers=args.fix_bottom_layers,
                layer_tolerance=args.layer_tolerance,
                mobile_indices_text=args.mobile_indices,
                adsorbate_elements=args.adsorbate_elements,
            ))
    else:
        if poscar is None:
            raise SkillError("--poscar is required")
        kpts = args.kpts or kpts_from_settings(settings)
        encut = args.encut if args.encut is not None else encut_from_settings(settings)
        # Load profile once to obtain default kpts if not explicitly supplied.
        profile_name, _, params_preview = get_vasp_params(
            defaults,
            args.calc_type,
            profile_name=args.profile,
            overrides=overrides,
            allow_unverified=args.allow_unverified_profile,
        )
        if not kpts:
            if "kpts" not in params_preview:
                raise SkillError(f"No kpts provided and profile {profile_name!r} has no kpts. Use --kpts or --selected-settings.")
            kpts = [int(x) for x in params_preview["kpts"]]
        outdir = Path(args.outdir).expanduser().resolve() if args.outdir else infer_outdir(args.calc_type, project_root, kpts, encut, poscar)
        jobs.append(make_one_job(
            calc_type=args.calc_type,
            poscar=poscar,
            calc_dir=outdir,
            kpts=kpts,
            encut=encut,
            defaults=defaults,
            profile_name=args.profile,
            overrides=overrides,
            cores=cores,
            submit=args.submit,
            dry_run_submit=args.dry_run_submit,
            allow_unverified_profile=args.allow_unverified_profile,
            fix_bottom_layers=args.fix_bottom_layers,
            layer_tolerance=args.layer_tolerance,
            mobile_indices_text=args.mobile_indices,
            adsorbate_elements=args.adsorbate_elements,
        ))

    result = {"ok": True, "jobs": jobs}
    if args.write_summary:
        write_yaml(args.write_summary, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate VASP inputs using the vasp-lab-job skill.")
    parser.add_argument("--calc-type", required=True, choices=CALC_TYPES)
    parser.add_argument("--poscar", help="Input POSCAR or CONTCAR path. Required unless --scan-poscars is used.")
    parser.add_argument("--outdir", help="Output calculation directory for single-job modes.")
    parser.add_argument("--project-root", default=".", help="Project root used for inferred directory layout.")
    parser.add_argument("--parameters-yaml", default=str(Path(__file__).resolve().parent.parent / "references" / "defaults.yaml"))
    parser.add_argument("--profile", help="Parameter profile name in parameters YAML. Prefer literature profiles when available.")
    parser.add_argument("--allow-unverified-profile", action="store_true", help="Allow profiles marked as needing literature verification.")
    parser.add_argument("--selected-settings", help="YAML with selected_kpts and/or selected_encut.")
    parser.add_argument("--kpts", type=lambda s: parse_int_list(s, 3), help="Explicit mesh, e.g. '4 4 1' or '[4,4,1]'.")
    parser.add_argument("--encut", type=int, help="Explicit ENCUT override.")
    parser.add_argument("--kpoint-series", action="append", type=lambda s: parse_int_list(s, 3), help="Add a k-point mesh for slab-kconv. Can be repeated.")
    parser.add_argument("--encut-series", action="append", type=int, help="Add an ENCUT value for slab-encut. Can be repeated.")
    parser.add_argument("--set", action="append", help="Override ASE Vasp parameter as key=value. Can be repeated.")
    parser.add_argument("--cores", type=int, choices=[48, 64])
    parser.add_argument("--submit", action="store_true", help="Run qsub after input generation.")
    parser.add_argument("--dry-run-submit", action="store_true", help="Write inputs and submit script but do not call qsub.")
    parser.add_argument("--scan-poscars", help="Glob under project-root, e.g. 'POSCAR*', for ads/oxide-ads batch input generation.")
    parser.add_argument("--fix-bottom-layers", type=int, help="Set Selective Dynamics by fixing the bottom N z-layers.")
    parser.add_argument("--layer-tolerance", type=float, default=0.35, help="Å tolerance for grouping z-layers when using --fix-bottom-layers.")
    parser.add_argument("--mobile-indices", help="For freq: 1-based mobile atom indices/ranges; all others fixed, e.g. '97-104'.")
    parser.add_argument("--adsorbate-elements", nargs="+", help="For freq fallback: elements to keep mobile; all others fixed. Use --mobile-indices when elements overlap slab.")
    parser.add_argument("--write-summary", help="Write a summary YAML for all generated jobs.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = run(args)
    except SkillError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
