"""LLM provider adapters."""
from llm_eval.adapters.base import BaseAdapter
from llm_eval.adapters.openai_adapter import OpenAIAdapter
from llm_eval.adapters.anthropic_adapter import AnthropicAdapter


def get_adapter(provider: str, model: str | None = None) -> BaseAdapter:
    """Factory: get an adapter by provider name with optional model override."""
    provider = provider.lower()
    if provider == "openai":
        return OpenAIAdapter(model=model)
    if provider == "anthropic":
        return AnthropicAdapter(model=model)
    raise ValueError(f"Unknown provider: {provider}")


__all__ = ["BaseAdapter", "OpenAIAdapter", "AnthropicAdapter", "get_adapter"]
