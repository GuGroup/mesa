#!/usr/bin/env python3
"""Regression tests for calculator-specific Methods and citation gating."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COLLECTOR = load_module(
    "collect_methods_evidence",
    "methods/collect-methods-evidence/scripts/collect_methods_evidence.py",
)
SELECTOR = load_module(
    "select_citations",
    "general/select-citations/scripts/select_citations.py",
)
WRITER = load_module(
    "write_methods_sections",
    "methods/write-methods-sections/scripts/write_methods_sections.py",
)


class BackendPolicyTests(unittest.TestCase):
    def test_uma_only_drops_stale_dft_settings_from_methods_evidence(self) -> None:
        # Given a UMA strategy with stale DFT fields copied into dft_details.
        computational = {
            "methods": ["UMA relaxation and vibrational frequencies"],
            "models": ["slab"],
            "procedures": ["Build catalyst models with stale VASP settings", "Relax the structures"],
            "optimization": {"calculator": "VASP", "optimizer": "FIRE"},
            "dft_details": {
                "code": "VASP",
                "functional": "PBE",
                "pseudopotentials_or_paw": "PAW",
                "plane_wave_cutoff": 500,
                "k_point_mesh": "6x6x6",
            },
        }

        # When the collector resolves and applies the active backend policy.
        policy = COLLECTOR.resolve_backend_policy(computational)
        minimal = COLLECTOR.build_minimal_evidence(
            strategy_id="S1",
            computational=computational,
            model_manifest=None,
            gas_metadata=None,
            reference_policy=None,
            vib_summary=None,
            relax_summary=None,
            relaxation_registry=None,
            free_energy_bookkeeping=None,
            backend_policy=policy,
        )
        geometry = next(section for section in minimal["sections"] if section["section_id"] == "geometry_optimization")

        # Then the output exposes only the UMA branch and no DFT settings.
        self.assertEqual(policy["mode"], "uma_mlip")
        self.assertFalse(policy["allows_dft"])
        self.assertEqual(geometry["strategy_inputs"], {"methods": computational["methods"]})
        self.assertEqual(geometry["project_details"]["optimization"], {"optimizer": "FIRE"})
        self.assertEqual(geometry["procedure_inputs"], ["Relax the structures"])
        model = next(section for section in minimal["sections"] if section["section_id"] == "model_construction")
        self.assertEqual(model["procedure_inputs"], [])
        self.assertEqual(minimal["source_strategy_computational"]["dft_details"], {})

    def test_uma_only_rejects_dft_sentence_citations(self) -> None:
        # Given a UMA-only section and a source library containing DFT references.
        policy = COLLECTOR.resolve_backend_policy({"methods": ["UMA relaxation"]})
        section = {
            "backend_policy": policy,
            "sections": [{
                "section_id": "geometry_optimization",
                "content_blocks": [{"type": "paragraph", "text": "Geometry optimization used PBE and PAW settings."}],
            }],
        }
        sources = {
            "canonical_method_references": [
                {"source_id": "p", "citation_key": "Perdew1996", "source_role": "canonical_method_reference", "title": "PBE"},
                {"source_id": "b", "citation_key": "Blochl1994", "source_role": "canonical_method_reference", "title": "PAW"},
            ]
        }

        # When citation packets and deterministic decisions are produced.
        index = SELECTOR.build_index(sources)
        packets = SELECTOR.make_sentence_packets(section, index, 8, policy)
        decisions = SELECTOR.merge_decisions(packets, None)

        # Then no forbidden DFT citation is selected and the sentence is flagged.
        self.assertEqual(packets[0]["candidate_citations"], [])
        self.assertEqual(decisions[0]["selected_citation_keys"], [])
        self.assertTrue(decisions[0]["needs_human_check"])
        self.assertEqual(decisions[0]["backend_violations"], ["PBE", "PAW"])

    def test_writer_validation_rejects_dft_public_text_in_uma_mode(self) -> None:
        # Given a public Methods section that violates a UMA-only backend policy.
        policy = COLLECTOR.resolve_backend_policy({"methods": ["UMA relaxation"]})
        sections = [{
            "section_id": "geometry_optimization",
            "title": "Geometry optimization",
            "text": "VASP and PBE were used.",
            "content_blocks": [{"type": "paragraph", "text": "VASP and PBE were used."}],
        }]

        # When writer validation runs.
        report = WRITER.validate_output(sections, policy)

        # Then the output is rejected with backend-specific violations.
        self.assertFalse(report["ok"])
        self.assertEqual(report["section_reports"][0]["backend_forbidden_terms"], ["VASP", "PBE"])

    def test_documented_uma_mlip_override_is_recognized(self) -> None:
        # Given the backend-mode value documented by the collector CLI.
        computational = {"methods": ["VASP with PBE from stale strategy prose"]}

        # When the explicit override is resolved.
        policy = COLLECTOR.resolve_backend_policy(computational, override="uma_mlip")

        # Then the override selects UMA and suppresses the stale DFT branch.
        self.assertEqual(policy["mode"], "uma_mlip")
        self.assertFalse(policy["allows_dft"])

    def test_project_profile_backend_wins_over_stale_strategy_methods(self) -> None:
        # Given an authoritative UMA project profile and stale DFT strategy prose.
        computational = {"methods": ["UMA relaxation", "VASP with PBE"]}
        profile = "Calculation backend: UMA. Do not create VASP jobs."

        # When backend policy is resolved.
        policy = COLLECTOR.resolve_backend_policy(computational, project_profile_text=profile)

        # Then the project profile remains authoritative.
        self.assertEqual(policy["mode"], "uma_mlip")
        self.assertFalse(policy["allows_dft"])
        minimal = COLLECTOR.build_minimal_evidence(
            strategy_id="S1",
            computational=computational,
            model_manifest=None,
            gas_metadata=None,
            reference_policy=None,
            vib_summary=None,
            relax_summary=None,
            relaxation_registry=None,
            free_energy_bookkeeping=None,
            backend_policy=policy,
        )
        geometry = next(
            section
            for section in minimal["sections"]
            if section["section_id"] == "geometry_optimization"
        )
        self.assertEqual(geometry["strategy_inputs"]["methods"], ["UMA relaxation"])

    def test_disabled_thermodynamic_corrections_remain_disabled(self) -> None:
        # Given a DFT strategy that explicitly disables thermodynamic corrections.
        computational = {
            "methods": ["DFT relaxation"],
            "dft_details": {"thermodynamic_corrections": False},
        }
        policy = COLLECTOR.resolve_backend_policy(computational)

        # When Methods evidence is compacted.
        minimal = COLLECTOR.build_minimal_evidence(
            strategy_id="S1",
            computational=computational,
            model_manifest=None,
            gas_metadata=None,
            reference_policy=None,
            vib_summary=None,
            relax_summary=None,
            relaxation_registry=None,
            free_energy_bookkeeping=None,
            backend_policy=policy,
        )

        # Then no enabled Gibbs-correction formalism is introduced.
        self.assertNotIn("gibbs_correction", minimal["thermodynamic_formalism"])


if __name__ == "__main__":
    unittest.main()
