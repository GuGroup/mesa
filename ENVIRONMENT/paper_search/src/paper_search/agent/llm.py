from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Final

from paper_search.config import LlmConfig

OPENAI_OAUTH_BASE_URL: Final = "http://127.0.0.1:10531/v1"
OPENAI_OAUTH_API_KEY: Final = "openai-oauth-local"

# Default chat model per provider. Configurable via llm.model; may need updating
# to whatever model ids are live at run time.
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.4-mini",
    "openai-oauth": "gpt-5.4",
}

PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

_RESPONSE_CACHE_CONFIGURED = False


def effective_temperature(model: str | None, temperature: float) -> float:
    # OpenAI gpt-5 family only supports temperature=1; setting anything else
    # is silently overridden (with a warning), so make it explicit.
    if model and str(model).lower().lstrip("/").split("/")[-1].startswith("gpt-5"):
        return 1.0
    return temperature


def normalize_provider(llm: LlmConfig | None) -> str:
    if llm is None:
        return "none"
    return (llm.provider or "none").strip().lower().replace("_", "-")


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    if stripped.startswith("${") and stripped.endswith("}"):
        return None
    return stripped or None


def openai_base_url(llm: LlmConfig) -> str | None:
    base_url = _optional(llm.base_url)
    if base_url is not None:
        return base_url
    if normalize_provider(llm) == "openai-oauth":
        return OPENAI_OAUTH_BASE_URL
    return None


def openai_api_key(llm: LlmConfig) -> str | None:
    key_env = _optional(llm.api_key_env)
    if key_env is not None:
        key = _optional(os.environ.get(key_env))
        if key is not None:
            return key
    provider = normalize_provider(llm)
    if provider == "openai-oauth":
        return OPENAI_OAUTH_API_KEY
    default_key_env = PROVIDER_KEY_ENV.get(provider)
    if default_key_env is None:
        return None
    return _optional(os.environ.get(default_key_env))


def provider_enabled(llm: LlmConfig | None) -> bool:
    """True when a real LLM provider is configured *and* its API key is present.

    Drives full vs deterministic mode so the graph stays runnable offline.
    """
    provider = normalize_provider(llm)
    if provider in ("", "none"):
        return False
    if provider == "openai-oauth":
        return True
    key_env = PROVIDER_KEY_ENV.get(provider)
    if not key_env:
        return False
    return bool(os.environ.get(key_env))


def configure_response_cache(path: str | Path) -> None:
    """Install a global SQLite cache for prompt->completion pairs (idempotent)."""
    global _RESPONSE_CACHE_CONFIGURED
    if _RESPONSE_CACHE_CONFIGURED:
        return
    from langchain_community.cache import SQLiteCache
    from langchain_core.globals import set_llm_cache

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    set_llm_cache(SQLiteCache(database_path=str(path)))
    _RESPONSE_CACHE_CONFIGURED = True


def build_chat_model(llm: LlmConfig) -> Any | None:
    """Construct a LangChain chat model for the configured provider, or None."""
    provider = normalize_provider(llm)
    model = llm.model or DEFAULT_MODELS.get(provider)
    if not model:
        return None
    temperature = effective_temperature(model, llm.temperature)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=llm.max_tokens,
        )
    if provider in ("openai", "openai-oauth"):
        from langchain_openai import ChatOpenAI

        openai_kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "max_tokens": llm.max_tokens,
        }
        base_url = openai_base_url(llm)
        if base_url is not None:
            openai_kwargs["base_url"] = base_url
        api_key = openai_api_key(llm)
        if api_key is not None:
            openai_kwargs["api_key"] = api_key

        return ChatOpenAI(**openai_kwargs)
    return None


def cached_context_content(text: str, provider: str, prompt_cache: bool) -> Any:
    """Return system content that opts into provider prompt caching.

    Anthropic: a content block tagged ``cache_control: ephemeral`` so the shared
    corpus prefix is cached across calls. OpenAI: a plain string (prefix caching
    is automatic as long as the prefix is stable).
    """
    if provider == "anthropic" and prompt_cache:
        return [
            {
                "type": "text",
                "text": text,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    return text


def build_messages(
    *,
    system_context: str,
    human_prompt: str,
    provider: str,
    prompt_cache: bool,
) -> list[Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    return [
        SystemMessage(
            content=cached_context_content(system_context, provider, prompt_cache)
        ),
        HumanMessage(content=human_prompt),
    ]


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def parse_json_response(text: str) -> Any:
    """Best-effort JSON parse of an LLM response (handles ```json fences)."""
    text = (text or "").strip()
    if not text:
        return None
    match = _JSON_BLOCK_RE.search(text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        if start == -1:
            start = text.find("{")
        end = max(text.rfind("]"), text.rfind("}"))
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def message_text(response: Any) -> str:
    """Extract plain text from a LangChain chat response (str or block list)."""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)
