"""Evaluator registry. Each assertion type maps to an evaluator function."""
from llm_eval.evaluators import format as format_mod
from llm_eval.evaluators import semantic
from llm_eval.evaluators import behavioral
from llm_eval.evaluators import safety
from llm_eval.evaluators import operational


# Maps assertion type -> evaluator callable.
# Each evaluator: (assertion, result, context) -> AssertionResult
REGISTRY = {
    # format
    "json_schema": format_mod.eval_json_schema,
    "regex": format_mod.eval_regex,
    "max_length": format_mod.eval_max_length,
    "min_length": format_mod.eval_min_length,
    "no_truncation": format_mod.eval_no_truncation,
    # semantic
    "semantic_similarity": semantic.eval_semantic_similarity,
    "answer_relevancy": semantic.eval_answer_relevancy,
    "faithfulness": semantic.eval_faithfulness,
    "llm_as_judge": semantic.eval_llm_as_judge,
    # behavioral
    "instruction_compliance": behavioral.eval_instruction_compliance,
    "prompt_injection_resistance": behavioral.eval_prompt_injection_resistance,
    "consistency": behavioral.eval_consistency,
    "recency_check": behavioral.eval_recency_check,
    # safety
    "no_pii": safety.eval_no_pii,
    "no_toxicity": safety.eval_no_toxicity,
    # operational
    "max_latency_ms": operational.eval_max_latency,
}


# Categories used by the scorer. Maps assertion type to scoring bucket.
ASSERTION_CATEGORY = {
    "json_schema": "format",
    "regex": "format",
    "max_length": "format",
    "min_length": "format",
    "no_truncation": "format",
    "max_latency_ms": "format",
    "semantic_similarity": "accuracy",
    "answer_relevancy": "accuracy",
    "instruction_compliance": "accuracy",
    "consistency": "accuracy",
    "recency_check": "accuracy",
    "faithfulness": "hallucination",
    "llm_as_judge": "hallucination",
    "prompt_injection_resistance": "accuracy",
    "no_pii": "accuracy",
    "no_toxicity": "accuracy",
}
