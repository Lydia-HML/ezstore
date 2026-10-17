"""LLM 評審共用的模型呼叫：與 Agent 相同，依模型名稱選 OpenAI 或 Gemini。

評審模型取 JUDGE_MODEL，沒設就沿用 AGENT_MODEL（預設 gemini-3.8-flash）。
`openai/` 開頭走 LiteLLM（OPENAI_API_KEY），其他走 google-genai（GEMINI_API_KEY 或 Vertex AI）。
"""

import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

_AGENT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_AGENT_ROOT / ".env")
load_dotenv(_AGENT_ROOT.parent / ".env")

_local = threading.local()


def judge_model() -> str:
    return (
        os.environ.get("JUDGE_MODEL")
        or os.environ.get("AGENT_MODEL")
        or "gemini-3.8-flash"
    )


def _genai_client():
    # 每個評分執行緒一個 client（eval SDK 以執行緒池平行評分）。
    client = getattr(_local, "client", None)
    if client is None:
        from google import genai

        client = _local.client = genai.Client()
    return client


def ask[T: BaseModel](prompt: str, schema: type[T]) -> tuple[T | None, str]:
    """回傳 (解析後的結構, 原始文字)。模型沒給出可用結果時結構為 None。"""
    model = judge_model()
    if model.startswith("openai/"):
        import litellm

        litellm.drop_params = True
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format=schema,
            num_retries=2,
        )
        text = resp.choices[0].message.content or ""
        try:
            return schema.model_validate_json(text), text
        except ValueError:
            return None, text

    from google.genai import types

    resp = _genai_client().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    return resp.parsed, resp.text or ""
