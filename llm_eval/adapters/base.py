"""Abstract base class for LLM provider adapters."""
from abc import ABC, abstractmethod

from llm_eval.models import CompletionResult, ModelConfig


class BaseAdapter(ABC):
    """All adapters expose the same `complete()` interface so the runner
    treats providers uniformly."""

    @abstractmethod
    def complete(self, prompt: str, config: ModelConfig) -> CompletionResult:
        """Run a single completion. Must measure latency and capture model version."""

    @abstractmethod
    def name(self) -> str:
        """Lowercase provider name, e.g. 'openai'."""
