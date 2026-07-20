"""OpenAI adapter using the official openai SDK."""
from __future__ import annotations

import os
import time
import json

from llm_eval.adapters.base import BaseAdapter
from llm_eval.models import AgentStep, CompletionResult, ModelConfig, ToolCall


class OpenAIAdapter(BaseAdapter):
    """Wraps the openai SDK with our uniform interface.

    Model is configurable via OPENAI_MODEL env var (default gpt-4o-mini).
    Handles a single retry on rate limit errors with exponential backoff.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._client = None  # Lazy: only init when API key is needed.

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return self._client

    def name(self) -> str:
        return "openai"

    def complete(self, prompt: str, config: ModelConfig) -> CompletionResult:
        start = time.time()

        for attempt in range(2):
            try:
                client = self._get_client()
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                )
                latency_ms = int((time.time() - start) * 1000)
                text = response.choices[0].message.content or ""
                raw_tool_calls = getattr(response.choices[0].message, "tool_calls", None) or []
                tool_calls: list[ToolCall] = []
                for call in raw_tool_calls:
                    raw_arguments = getattr(call.function, "arguments", "{}")
                    try:
                        arguments = json.loads(raw_arguments)
                    except (TypeError, json.JSONDecodeError):
                        arguments = {"_raw": str(raw_arguments)}
                    tool_calls.append(ToolCall(
                        name=call.function.name,
                        arguments=arguments,
                        call_id=getattr(call, "id", ""),
                    ))
                tokens = response.usage.total_tokens if response.usage else 0
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
                    time.sleep(2)  # exponential backoff: single retry
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
