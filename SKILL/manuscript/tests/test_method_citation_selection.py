#!/usr/bin/env python3
"""Regression tests for LLM-grounded canonical method citations."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SELECTOR = load_module(
    "select_citations_llm_grounding",
    "general/select-citations/scripts/select_citations.py",
)
EXTRACTOR = load_module(
    "extract_citation_sources_identity",
    "general/extract-citation-sources/scripts/extract_citation_sources.py",
)


def canonical_source(
    citation_key: str,
    title: str,
    method_tags: list[str],
    backend_family: str,
) -> dict:
    return {
        "source_id": f"M-{citation_key}",
        "reference_id": f"M-{citation_key}",
        "citation_key": citation_key,
        "source_role": "canonical_method_reference",
        "title": title,
        "authors": ["A. Author"],
        "year": "2024",
        "doi": f"10.0000/{citation_key.lower()}",
        "method_tags": method_tags,
        "backend_family": backend_family,
        "citation_guidance": "Use only when the named method was actually used.",
    }


class LlmMethodCitationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = {
            "primary_papers": [{
                "paper_id": "P001",
                "citation_key": "ProjectPBE2024",
                "source_role": "primary_project_pdf",
                "title": "PBE study of a catalyst",
                "authors": ["P. Author"],
                "year": "2024",
                "doi": "10.0000/project-pbe",
            }],
            "canonical_method_references": [
                canonical_source("Perdew1996", "PBE functional", ["PBE"], "dft"),
                canonical_source("Hammer1999", "RPBE functional", ["RPBE"], "dft"),
                canonical_source("Kresse1996", "VASP", ["VASP", "plane wave"], "dft"),
                canonical_source("UMA2025", "UMA", ["UMA", "FAIRChem"], "uma_mlip"),
                canonical_source("ASE2017", "ASE", ["ASE"], "general"),
            ]
        }

    def test_methods_packet_exposes_complete_canonical_metadata_without_scores(self) -> None:
        # Given a Methods sentence and a bounded canonical source library.
        section = {
            "backend_policy": {"mode": "dft"},
            "sections": [{
                "section_id": "geometry_optimization",
                "content_blocks": [{"type": "paragraph", "text": "The PBE functional was used."}],
            }],
        }

        # When the selector builds the LLM packet.
        packets = SELECTOR.make_sentence_packets(
            section,
            SELECTOR.build_index(self.sources),
            8,
            section["backend_policy"],
        )
        llm_packet = SELECTOR.build_llm_packets(packets)[0]

        # Then eligible canonical references are provided as metadata, not scores or forced keys.
        keys = {candidate["citation_key"] for candidate in llm_packet["candidates"]}
        self.assertIn("Perdew1996", keys)
        self.assertIn("Hammer1999", keys)
        self.assertNotIn("UMA2025", keys)
        self.assertNotIn("required_citation_keys", llm_packet)
        for candidate in llm_packet["candidates"]:
            self.assertNotIn("score", candidate)
            self.assertNotIn("retrieval_score", candidate)
            if candidate["source_role"] == "canonical_method_reference":
                self.assertIn("method_tags", candidate)
                self.assertIn("backend_family", candidate)
                self.assertIn("citation_guidance", candidate)

    def test_generic_cutoff_does_not_force_a_vasp_citation_without_llm(self) -> None:
        # Given a generic cutoff sentence that does not identify VASP as the active method.
        section = {
            "backend_policy": {"mode": "dft"},
            "sections": [{
                "section_id": "vibrational_free_energy_corrections",
                "content_blocks": [{
                    "type": "paragraph",
                    "text": "Modes below a frequency cutoff were excluded.",
                }],
            }],
        }
        packets = SELECTOR.make_sentence_packets(
            section,
            SELECTOR.build_index(self.sources),
            8,
            section["backend_policy"],
        )

        # When deterministic fallback is used.
        decision = SELECTOR.merge_decisions(packets, None)[0]

        # Then no VASP citation is guessed and the method-citation decision is left for review.
        self.assertEqual(decision["selected_citation_keys"], [])
        self.assertTrue(decision["needs_human_check"])
        for candidate in decision["candidate_citations"]:
            self.assertNotIn("score", candidate)

    def test_quantum_espresso_plane_wave_sentence_does_not_force_kresse(self) -> None:
        # Given a non-VASP plane-wave sentence.
        section = {
            "backend_policy": {"mode": "dft"},
            "sections": [{
                "section_id": "geometry_optimization",
                "content_blocks": [{
                    "type": "paragraph",
                    "text": "Quantum ESPRESSO used a plane-wave cutoff of 500 eV.",
                }],
            }],
        }
        packets = SELECTOR.make_sentence_packets(
            section,
            SELECTOR.build_index(self.sources),
            8,
            section["backend_policy"],
        )

        # When no LLM decision is available.
        decision = SELECTOR.merge_decisions(packets, None)[0]

        # Then Kresse1996 is not selected by lexical scoring.
        self.assertNotIn("Kresse1996", decision["selected_citation_keys"])

    def test_llm_method_choice_is_bounded_to_supplied_candidates(self) -> None:
        # Given a PBE Methods sentence and eligible canonical candidates.
        section = {
            "backend_policy": {"mode": "dft"},
            "sections": [{
                "section_id": "geometry_optimization",
                "content_blocks": [{"type": "paragraph", "text": "The PBE functional was used."}],
            }],
        }
        packets = SELECTOR.make_sentence_packets(
            section,
            SELECTOR.build_index(self.sources),
            8,
            section["backend_policy"],
        )

        # When the LLM selects one valid key and one key outside the bounded packet.
        normalized = SELECTOR.normalize_llm_decisions(
            packets,
            {
                "decisions": [{
                    "sentence_id": "S001",
                    "citation_keys": ["Perdew1996", "OutsideKey"],
                    "confidence": "high",
                    "needs_human_check": False,
                    "reason": "The sentence explicitly reports PBE use.",
                }]
            },
        )
        decision = SELECTOR.merge_decisions(packets, normalized)[0]

        # Then only the bounded canonical reference is retained as an LLM decision.
        self.assertEqual(decision["selected_citation_keys"], ["Perdew1996"])
        self.assertEqual(decision["decision_source"], "llm")
        cited = SELECTOR.apply_annotations(
            section,
            [decision],
            SELECTOR.source_lookup_from_index(SELECTOR.build_index(self.sources)),
            section["backend_policy"],
        )
        self.assertEqual(cited["citation_sources_used"][0]["citation_key"], "Perdew1996")
        annotation = cited["sections"][0]["content_blocks"][0]["citation_annotations"][0]
        self.assertNotIn("required_citation_keys", annotation)


class CanonicalIdentityTests(unittest.TestCase):
    def test_canonical_keys_are_reserved_and_same_doi_second_neighbors_are_removed(self) -> None:
        # Given a generated second-neighbor record that duplicates a canonical DOI and key.
        canonical = [{
            "citation_key": "Kresse1996",
            "doi": "10.1103/PhysRevB.54.11169",
            "source_role": "canonical_method_reference",
        }]
        second_neighbors = [{
            "citation_key": "Kresse1996",
            "doi": "10.1103/PhysRevB.54.11169",
            "source_role": "second_neighbor_reference",
        }]

        # When canonical identity is merged into the extracted source library.
        merged_second, merged_canonical = EXTRACTOR.merge_canonical_references(
            second_neighbors,
            canonical,
        )

        # Then the canonical record owns the DOI and citation key deterministically.
        self.assertEqual(merged_second, [])
        self.assertEqual(merged_canonical, canonical)


if __name__ == "__main__":
    unittest.main()
