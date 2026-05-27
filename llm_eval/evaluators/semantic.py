"""Semantic evaluators: meaning-level checks via embeddings and LLM-as-judge."""
from __future__ import annotations

import os
import re
from typing import Any

from llm_eval.models import Assertion, AssertionResult, CompletionResult


# Module-level cache for the sentence-transformer model (it's expensive to load).
_st_model = None


def _get_embedder():
    """Lazy-load all-MiniLM-L6-v2. Cached at module level."""
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _st_model


def cosine_similarity(a, b) -> float:
    """Compute cosine similarity between two 1-D vectors."""
    import numpy as np
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _embed_text(text: str):
    model = _get_embedder()
    return model.encode(text, convert_to_numpy=True)


def eval_semantic_similarity(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    reference = assertion.params.get("reference", "")
    threshold = float(assertion.params.get("threshold", 0.7))

    if not reference:
        return AssertionResult(
            type=assertion.type, passed=False, score=0.0,
            detail="No reference text provided",
        )

    try:
        ref_emb = _embed_text(reference)
        resp_emb = _embed_text(result.text)
        score = cosine_similarity(ref_emb, resp_emb)
    except Exception as exc:  # noqa: BLE001
        return AssertionResult(
            type=assertion.type, passed=False, score=0.0,
            detail=f"Embedding failed: {exc}",
        )

    passed = score >= threshold
    return AssertionResult(
        type=assertion.type, passed=passed, score=float(score),
        detail=f"Similarity {score:.3f} {'>=' if passed else '<'} threshold {threshold}",
    )


def _judge_score(rubric: str, text: str) -> float:
    """Call the first available LLM provider as a judge.

    Returns a float 0-1 parsed from the model's reply, or 0.5 on failure.
    """
    from llm_eval.adapters import get_adapter
    from llm_eval.models import ModelConfig

    judge_prompt = (
        "You are an impartial evaluator. Score the following response on a scale "
        "from 0.0 to 1.0. Return ONLY a single number between 0 and 1, nothing else.\n\n"
        f"Rubric: {rubric}\n\n"
        f"Response to evaluate:\n{text}\n\n"
        "Score (0.0-1.0):"
    )

    # Prefer OpenAI if key present, else Anthropic.
    provider = "openai" if os.getenv("OPENAI_API_KEY") else "anthropic"
    try:
        adapter = get_adapter(provider)
        out = adapter.complete(judge_prompt, ModelConfig(temperature=0.0, max_tokens=10))
        if out.error:
            return 0.5
        match = re.search(r"[01](?:\.\d+)?", out.text)
        if not match:
            return 0.5
        return max(0.0, min(1.0, float(match.group(0))))
    except Exception:  # noqa: BLE001
        return 0.5


def eval_answer_relevancy(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    question = assertion.params.get("question", context.get("prompt", ""))
    threshold = float(assertion.params.get("threshold", 0.7))
    rubric = f"Does this response answer the question: '{question}'? Score 1.0 if highly relevant, 0.0 if irrelevant."
    score = _judge_score(rubric, result.text)
    passed = score >= threshold
    return AssertionResult(
        type=assertion.type, passed=passed, score=score,
        detail=f"Relevancy {score:.2f} {'>=' if passed else '<'} threshold {threshold}",
    )


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 3]


def _grounding_score(response: str, ctx_text: str) -> float:
    """Mean of per-response-sentence max cosine similarity against context sentences.

    Catches fabricated content that an LLM judge may rate as plausible: if a
    response sentence has no semantic neighbor in the context, its max-sim is
    low and drags the mean down.
    """
    resp_sents = _split_sentences(response)
    ctx_sents = _split_sentences(ctx_text)
    if not resp_sents or not ctx_sents:
        return 0.0
    model = _get_embedder()
    resp_embs = model.encode(resp_sents, convert_to_numpy=True)
    ctx_embs = model.encode(ctx_sents, convert_to_numpy=True)
    per_sent_max = []
    for r_emb in resp_embs:
        sims = [cosine_similarity(r_emb, c_emb) for c_emb in ctx_embs]
        per_sent_max.append(max(sims))
    return float(sum(per_sent_max) / len(per_sent_max))


def eval_faithfulness(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    """Hybrid faithfulness: min(LLM-judge, embedding-grounding).

    The judge catches semantic contradictions; the grounding score catches
    plausible-sounding fabrications the judge tends to miss (see semantic.py
    comments and book's failure-mode taxonomy).
    """
    ctx_text = assertion.params.get("context", "")
    threshold = float(assertion.params.get("threshold", 0.8))

    if not ctx_text:
        return AssertionResult(
            type=assertion.type, passed=False, score=0.0,
            detail="No context provided for faithfulness check",
        )

    rubric = (
        f"Is EVERY claim in this response supported by the following context? "
        f"Score 1.0 if fully grounded, 0.0 if it hallucinates. "
        f"Context: {ctx_text}"
    )
    judge_score = _judge_score(rubric, result.text)

    try:
        grounding = _grounding_score(result.text, ctx_text)
    except Exception as exc:  # noqa: BLE001
        return AssertionResult(
            type=assertion.type, passed=judge_score >= threshold, score=judge_score,
            detail=f"Judge {judge_score:.2f} (grounding check failed: {exc})",
        )

    score = min(judge_score, grounding)
    passed = score >= threshold
    return AssertionResult(
        type=assertion.type, passed=passed, score=score,
        detail=(
            f"Faithfulness {score:.2f} {'>=' if passed else '<'} threshold {threshold} "
            f"(judge={judge_score:.2f}, grounding={grounding:.2f})"
        ),
    )


def eval_llm_as_judge(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    rubric = assertion.params.get("rubric", "Rate the overall quality of this response.")
    threshold = float(assertion.params.get("threshold", 0.7))
    score = _judge_score(rubric, result.text)
    passed = score >= threshold
    return AssertionResult(
        type=assertion.type, passed=passed, score=score,
        detail=f"Judge {score:.2f} {'>=' if passed else '<'} threshold {threshold}",
    )
