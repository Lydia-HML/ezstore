"""LLM-as-judge：`custom_response_quality`（1–5 分，見 eval_config.yaml）。

評審模型與 Agent 相同（OpenAI 或 Gemini），見 _judge.py。
多輪案例沒有 prompt 欄位，因此只用 response 與 agent_data。
"""

import sys
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _judge import ask


class _Verdict(BaseModel):
    score: int  # 1-5
    explanation: str


def evaluate(instance):
    reference = instance.get("reference")
    rubric = (
        "Grade the agent's final response on a 1-5 scale (1 poor, 5 excellent) for "
        "accuracy, relevance, and clarity."
    )
    if reference:
        rubric += (
            " The response should agree with the expected answer below; penalize "
            "factual disagreement with it."
        )
    prompt = (
        f"You are an expert QA evaluator for an enterprise AI assistant. {rubric}\n"
        "The user's messages are inside the Full Agent Trace.\n"
        f"Final Response: {instance.get('response', '')}\n"
    )
    if reference:
        prompt += f"Expected Answer (ground truth): {reference}\n"
    prompt += f"Full Agent Trace: {instance.get('agent_data', '')}\n"
    prompt += 'Return JSON: {"score": <1-5>, "explanation": "<one sentence>"}'

    verdict, raw = ask(prompt, _Verdict)
    if verdict is None:
        return {"score": 0, "explanation": raw}
    return {"score": max(1, min(5, verdict.score)), "explanation": verdict.explanation}
