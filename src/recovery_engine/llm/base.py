"""LLM client protocol + config (Section 14)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ChatError(RuntimeError):
    """Any failure talking to the provider. Callers fall back deterministically."""


@dataclass(frozen=True)
class LLMConfig:
    provider: str          # "openrouter" | "groq"
    model: str
    base_url: str
    api_key: str | None = None
    timeout: float = 30.0


@runtime_checkable
class LLMClient(Protocol):
    @property
    def available(self) -> bool:
        """True only if the client is configured with a usable API key."""

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> str: ...
