"""OpenAI-compatible client for OpenRouter / Groq (Section 14).

Both providers speak the OpenAI `/chat/completions` schema, so one thin client
serves both — selected by env. No provider SDK is required (uses httpx).

Env:
  LLM_PROVIDER   openrouter | groq              (default: openrouter)
  LLM_MODEL      overrides the per-provider default
  LLM_API_KEY    (or OPENROUTER_API_KEY / GROQ_API_KEY)
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

from .base import ChatError, LLMConfig

_PROVIDER_BASE = {
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
}

# Sensible free / low-cost defaults; override with LLM_MODEL.
_PROVIDER_DEFAULT_MODEL = {
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "groq": "llama-3.3-70b-versatile",
}


class OpenAICompatClient:
    def __init__(self, config: LLMConfig):
        self._config = config

    @property
    def available(self) -> bool:
        return bool(self._config.api_key)

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> str:
        if not self.available:
            raise ChatError("no API key configured")
        payload = {
            "model": self._config.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        try:
            resp = httpx.post(
                f"{self._config.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self._config.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ChatError(str(exc)) from exc


def from_env() -> Optional[OpenAICompatClient]:
    """Build a client from environment, or None if unconfigured.

    Returning None (rather than raising) lets the narrator run deterministically
    whenever no key is present.
    """
    provider = os.environ.get("LLM_PROVIDER", "openrouter").lower()
    if provider not in _PROVIDER_BASE:
        return None
    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get(f"{provider.upper()}_API_KEY")
    )
    if not api_key:
        return None
    model = os.environ.get("LLM_MODEL", _PROVIDER_DEFAULT_MODEL[provider])
    return OpenAICompatClient(
        LLMConfig(
            provider=provider,
            model=model,
            base_url=_PROVIDER_BASE[provider],
            api_key=api_key,
        )
    )
