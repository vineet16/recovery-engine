"""Provider-abstracted LLM interface (ARCHITECTURE.md Section 14).

The interface is thin and swappable. The narrator (Section 10) is the only
subsystem that touches it, and it is *optional*: everything works deterministically
with no client, and an OpenRouter/Groq client only enhances phrasing and freeform
answer interpretation. The LLM never decides the law (principle Section 2.2).
"""

from .base import ChatError, LLMClient, LLMConfig
from .openai_compat import OpenAICompatClient, from_env

__all__ = ["LLMClient", "LLMConfig", "ChatError", "OpenAICompatClient", "from_env"]
