"""Anthropic adapter using the official anthropic SDK."""
from __future__ import annotations

import os
import time

from llm_eval.adapters.base import BaseAdapter
from llm_eval.models import AgentStep, CompletionResult, ModelConfig, ToolCall


class AnthropicAdapter(BaseAdapter):
    """Wraps the anthropic SDK with our uniform interface.

    Model is configurable via ANTHROPIC_MODEL env var (default claude-3-5-haiku-latest).
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        return self._client

    def name(self) -> str:
        return "anthropic"

    # Models that have deprecated the `temperature` parameter (Anthropic-side).
    _NO_TEMPERATURE_MODELS = ("claude-opus-4-7", "claude-opus-4-8")

    def _supports_temperature(self) -> bool:
        return not any(self.model.startswith(m) for m in self._NO_TEMPERATURE_MODELS)

    def complete(self, prompt: str, config: ModelConfig) -> CompletionResult:
        start = time.time()

        for attempt in range(2):
            try:
                client = self._get_client()
                kwargs: dict = {
                    "model": self.model,
                    "max_tokens": config.max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if self._supports_temperature():
                    kwargs["temperature"] = config.temperature
                response = client.messages.create(**kwargs)
                latency_ms = int((time.time() - start) * 1000)
                # Anthropic returns a list of content blocks; concat text blocks.
                parts: list[str] = []
                tool_calls: list[ToolCall] = []
                for block in response.content:
                    if getattr(block, "type", None) == "text":
                        parts.append(block.text)
                    elif getattr(block, "type", None) == "tool_use":
                        tool_calls.append(ToolCall(
                            name=block.name,
                            arguments=block.input or {},
                            call_id=getattr(block, "id", ""),
                        ))
                text = "".join(parts)
                tokens = 0
                if response.usage:
                    tokens = response.usage.input_tokens + response.usage.output_tokens
                return CompletionResult(
                    text=text,
                    latency_ms=latency_ms,
                    tokens_used=tokens,
                    model_version=response.model or self.model,
                    tool_calls=tool_calls,
                    trajectory=[AgentStep(kind="tool_call", name=call.name) for call in tool_calls],
                )
            except Exception as exc:  # noqa: BLE001
                err_name = exc.__class__.__name__
                is_rate = "RateLimit" in err_name or "429" in str(exc)
                if is_rate and attempt == 0:
                    time.sleep(2)
                    start = time.time()
                    continue
                latency_ms = int((time.time() - start) * 1000)
                return CompletionResult(
                    text="",
                    latency_ms=latency_ms,
                    tokens_used=0,
                    model_version=self.model,
                    error=f"{err_name}: {exc}",
                )

        return CompletionResult(
            text="",
            latency_ms=0,
            tokens_used=0,
            model_version=self.model,
            error="unreachable",
        )
