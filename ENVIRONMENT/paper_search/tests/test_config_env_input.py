from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paper_search.config import PipelineConfig
from paper_search.run_input import load_run_input


class ConfigEnvInputTests(unittest.TestCase):
    def test_home_dotenv_is_loaded_when_workdir_has_no_env(self) -> None:
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cwd:
            Path(home, ".env").write_text(
                "\n".join(
                    [
                        "PAPER_SEARCH_EMAIL=home@example.invalid",
                        "SEMANTIC_SCHOLAR_API_KEY=home-s2-marker",
                        "PAPER_SEARCH_PROVIDER=openai-oauth",
                        "PAPER_SEARCH_MODEL=gpt-home",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"HOME": home}, clear=True):
                config = PipelineConfig.from_sources(
                    output_dir=Path(cwd) / "out", cwd=Path(cwd)
                )

            self.assertEqual(config.email, "home@example.invalid")
            self.assertEqual(config.semantic_scholar_api_key, "home-s2-marker")
            self.assertEqual(config.llm.provider, "openai-oauth")
            self.assertEqual(config.llm.model, "gpt-home")
            self.assertTrue(config.scihub_enabled)

    def test_workdir_dotenv_overrides_home_dotenv_without_overriding_shell(self) -> None:
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cwd:
            Path(home, ".env").write_text(
                "PAPER_SEARCH_EMAIL=home@example.invalid\n"
                "SEMANTIC_SCHOLAR_API_KEY=home-s2-marker\n",
                encoding="utf-8",
            )
            Path(cwd, ".env").write_text(
                "PAPER_SEARCH_EMAIL=cwd@example.invalid\n"
                "SEMANTIC_SCHOLAR_API_KEY=cwd-s2-marker\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"HOME": home, "PAPER_SEARCH_EMAIL": "shell@example.invalid"},
                clear=True,
            ):
                config = PipelineConfig.from_sources(
                    output_dir=Path(cwd) / "out", cwd=Path(cwd)
                )

            self.assertEqual(config.email, "shell@example.invalid")
            self.assertEqual(config.semantic_scholar_api_key, "cwd-s2-marker")

    def test_run_input_yaml_parses_search_agent_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "search-input.yaml"
            path.write_text(
                "\n".join(
                    [
                        "material: RuO2",
                        "reaction: HER",
                        "extra_terms:",
                        "  - rutile",
                        "  - heterointerface",
                        "research:",
                        "  prompt: Compare Ru/RuO2 interfaces for HER.",
                        "  collaboration_context: Experimental RuO2 samples include Ru.",
                        "  decision_criteria:",
                        "    - prioritize DFT-feasible surface gaps",
                        "  target_properties:",
                        "    - hydrogen adsorption free energy",
                        "  constraints:",
                        "    - no abstract-only evidence extraction",
                        "  calculation_preferences:",
                        "    - facet-resolved slab models",
                    ]
                ),
                encoding="utf-8",
            )

            run_input = load_run_input(path)

        self.assertEqual(run_input.material, "RuO2")
        self.assertEqual(run_input.reaction, "HER")
        self.assertEqual(run_input.extra_terms, ["rutile", "heterointerface"])
        self.assertEqual(
            run_input.research.prompt, "Compare Ru/RuO2 interfaces for HER."
        )
        self.assertEqual(
            run_input.research.collaboration_context,
            "Experimental RuO2 samples include Ru.",
        )
        self.assertEqual(
            run_input.research.decision_criteria,
            ["prioritize DFT-feasible surface gaps"],
        )
        self.assertEqual(
            run_input.research.target_properties,
            ["hydrogen adsorption free energy"],
        )
        self.assertEqual(
            run_input.research.constraints,
            ["no abstract-only evidence extraction"],
        )
        self.assertEqual(
            run_input.research.calculation_preferences,
            ["facet-resolved slab models"],
        )


if __name__ == "__main__":
    unittest.main()
