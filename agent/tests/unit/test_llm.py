"""模型供應商切換（quotation_agent/llm.py）。"""

import pytest
from google.adk.models import Gemini
from google.adk.models.lite_llm import LiteLlm

from quotation_agent import llm

CRED_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "OPENAI_API_KEY",
)


@pytest.fixture
def no_creds(monkeypatch):
    for name in CRED_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_default_model_is_gemini(monkeypatch):
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    assert llm.model_name() == "gemini-3.8-flash"


def test_openai_prefix_builds_litellm():
    assert isinstance(llm.build_model("openai/gpt-5-mini"), LiteLlm)


def test_gemini_name_builds_gemini():
    assert isinstance(llm.build_model("gemini-3.8-flash"), Gemini)


def test_openai_needs_openai_key(no_creds):
    no_creds.setenv("GEMINI_API_KEY", "x")
    assert not llm.has_credentials("openai/gpt-5-mini")
    no_creds.setenv("OPENAI_API_KEY", "x")
    assert llm.has_credentials("openai/gpt-5-mini")


def test_gemini_ignores_openai_key(no_creds):
    no_creds.setenv("OPENAI_API_KEY", "x")
    assert not llm.has_credentials("gemini-3.8-flash")
    no_creds.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    no_creds.setenv("GOOGLE_CLOUD_PROJECT", "p")
    assert llm.has_credentials("gemini-3.8-flash")


def test_missing_message_names_the_right_key():
    assert "OPENAI_API_KEY" in llm.missing_credentials_message("openai/gpt-5-mini")
    assert "GEMINI_API_KEY" in llm.missing_credentials_message("gemini-3.8-flash")
