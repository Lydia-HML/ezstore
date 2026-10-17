"""依 AGENT_MODEL 選擇意圖分類節點使用的模型供應商。

- `openai/` 開頭（例如 openai/gpt-5-mini）：透過 ADK 的 LiteLlm 呼叫 OpenAI，讀 OPENAI_API_KEY。
- 其他值（預設 gemini-3.8-flash）：Gemini，讀 GEMINI_API_KEY 或 Vertex AI 設定。

只有意圖分類節點會呼叫 LLM，所以換供應商只影響這一個節點。
"""

import os

from google.adk.models import Gemini
from google.adk.models.base_llm import BaseLlm
from google.genai import types

DEFAULT_MODEL = "gemini-3.8-flash"
OPENAI_PREFIX = "openai/"


def model_name() -> str:
    return os.environ.get("AGENT_MODEL") or DEFAULT_MODEL


def is_openai(model: str) -> bool:
    return model.startswith(OPENAI_PREFIX)


def build_model(model: str) -> BaseLlm:
    if is_openai(model):
        import litellm
        from google.adk.models.lite_llm import LiteLlm

        # 部分 OpenAI 模型（例如 gpt-5 系列）不接受 temperature=0，交給 LiteLLM 自動略過。
        litellm.drop_params = True
        return LiteLlm(model=model, num_retries=2)
    return Gemini(model=model, retry_options=types.HttpRetryOptions(attempts=3))


def has_credentials(model: str) -> bool:
    if is_openai(model):
        return bool(os.environ.get("OPENAI_API_KEY"))
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return True
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in (
        "1",
        "true",
    )
    return use_vertex and bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))


def missing_credentials_message(model: str) -> str:
    if is_openai(model):
        hint = f"目前模型是 {model}，請在專案根目錄的 .env 設定 OPENAI_API_KEY"
    else:
        hint = (
            f"目前模型是 {model}，請在專案根目錄的 .env 設定 GEMINI_API_KEY（或 Vertex AI 的 "
            "GOOGLE_GENAI_USE_VERTEXAI=true 與 GOOGLE_CLOUD_PROJECT）"
        )
    return f"智能助理尚未設定模型憑證，無法處理對話。{hint}，再重新啟動 agent 服務。"
