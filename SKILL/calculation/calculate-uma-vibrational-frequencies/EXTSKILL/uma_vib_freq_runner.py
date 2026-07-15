#!/usr/bin/env python3
"""Fixed UMA/ASE vibrational frequency runner for calculate-uma-vibrational-frequencies."""

import json
from pathlib import Path


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def main():
    config_path = Path("results/resolved_uma_vib_config.json")
    result_json = "results/uma_vib_freq.json"

    try:
        from ase.io import read
        from ase.vibrations import Vibrations
        from fairchem.core import FAIRChemCalculator, pretrained_mlip

        config = load_json(config_path)

        input_poscar = config["input_poscar"]
        output_freq = config["output_freq"]
        result_json = config["result_json"]
        vib_cache = config["vib_cache"]

        model = config["uma"]["model"]
        task_name = config["uma"]["task_name"]
        device = config["uma"]["device"]

        indices = config["vibration"].get("indices")
        delta = config["vibration"]["delta"]
        nfree = config["vibration"]["nfree"]

        atoms = read(input_poscar, format="vasp")

        predictor = pretrained_mlip.get_predict_unit(model, device=device)
        atoms.calc = FAIRChemCalculator(predictor, task_name=task_name)

        vib = Vibrations(
            atoms,
            indices=indices,
            name=vib_cache,
            delta=delta,
            nfree=nfree,
        )

        vib.run()

        frequencies = vib.get_frequencies()
        vib.summary(log=output_freq)

        result = {
            "status": "success",
            "runner": "uma_vib_freq_runner",
            "input": input_poscar,
            "output": output_freq,
            "config": str(config_path),
            "vib_cache": vib_cache,
            "results": {
                "n_atoms": len(atoms),
                "n_displaced_atoms": len(indices) if indices is not None else len(atoms),
                "n_modes": len(frequencies),
                "frequencies_cm_minus_1": [float(frequency.real) for frequency in frequencies],
                "n_imaginary_modes": int(sum(1 for frequency in frequencies if frequency.real < 0)),
                "has_imaginary_frequency": bool(any(frequency.real < 0 for frequency in frequencies)),
                "zero_point_energy_ev": float(vib.get_zero_point_energy()),
            },
            "errors": [],
        }

    except Exception as exc:  # noqa: BLE001 - always leave structured runner metadata.
        result = {
            "status": "failure",
            "runner": "uma_vib_freq_runner",
            "config": str(config_path),
            "errors": [
                {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            ],
        }

    write_json(result_json, result)


if __name__ == "__main__":
    main()
