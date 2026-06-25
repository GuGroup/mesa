from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from paper_search.agent.llm import (
    OPENAI_OAUTH_API_KEY,
    OPENAI_OAUTH_BASE_URL,
    build_chat_model,
    provider_enabled,
)
from paper_search.agent.paperqa_index import build_settings
from paper_search.config import LlmConfig, PaperQAConfig


class OpenAIOAuthTests(unittest.TestCase):
    def test_provider_does_not_require_openai_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(provider_enabled(LlmConfig(provider="openai-oauth")))
            self.assertTrue(provider_enabled(LlmConfig(provider="openai_oauth")))

    def test_chat_model_uses_local_proxy(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            chat_model = build_chat_model(
                LlmConfig(provider="openai-oauth", model="gpt-5.4")
            )

        self.assertIsNotNone(chat_model)
        self.assertEqual(getattr(chat_model, "model_name"), "gpt-5.4")
        self.assertEqual(getattr(chat_model, "openai_api_base"), OPENAI_OAUTH_BASE_URL)
        api_key = getattr(chat_model, "openai_api_key")
        self.assertEqual(api_key.get_secret_value(), OPENAI_OAUTH_API_KEY)

    def test_paperqa_settings_use_proxy_and_local_embeddings(self) -> None:
        __import__("paperqa")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "paper_search.agent.paperqa_index.importlib.util.find_spec",
                return_value=object(),
            ),
        ):
            settings = build_settings(
                LlmConfig(provider="openai-oauth", model="gpt-5.4"),
                PaperQAConfig(),
            )

        self.assertEqual(settings.llm, "openai/gpt-5.4")
        self.assertEqual(settings.summary_llm, "openai/gpt-5.4")
        self.assertEqual(settings.embedding, "st-multi-qa-MiniLM-L6-cos-v1")
        params = settings.llm_config["model_list"][0]["litellm_params"]
        self.assertEqual(params["api_base"], OPENAI_OAUTH_BASE_URL)
        self.assertEqual(params["api_key"], OPENAI_OAUTH_API_KEY)

    def test_paperqa_openai_embeddings_use_embedding_key_only(self) -> None:
        with patch.dict(
            os.environ, {"OPENAI_EMBEDDING_KEY": "embedding-key"}, clear=True
        ):
            settings = build_settings(
                LlmConfig(provider="openai-oauth", model="gpt-5.4"),
                PaperQAConfig(embedding="text-embedding-3-small"),
            )

        llm_params = settings.llm_config["model_list"][0]["litellm_params"]
        self.assertEqual(llm_params["api_key"], OPENAI_OAUTH_API_KEY)
        self.assertEqual(
            settings.embedding_config["kwargs"]["api_key"], "embedding-key"
        )

    def test_openai_api_key_does_not_select_openai_embeddings(self) -> None:
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "chat-key"}, clear=True),
            patch(
                "paper_search.agent.paperqa_index.importlib.util.find_spec",
                return_value=object(),
            ),
        ):
            settings = build_settings(
                LlmConfig(provider="openai-oauth", model="gpt-5.4"),
                PaperQAConfig(),
            )

        self.assertEqual(settings.embedding, "st-multi-qa-MiniLM-L6-cos-v1")
        self.assertIsNone(settings.embedding_config)

    def test_openai_embedding_requires_embedding_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_EMBEDDING_KEY"):
                build_settings(
                    LlmConfig(provider="openai-oauth", model="gpt-5.4"),
                    PaperQAConfig(embedding="text-embedding-3-small"),
                )
