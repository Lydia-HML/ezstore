"""Workflow 的離線整合測試。

意圖分類節點的 LLM 以固定回應取代（不需 API key），其餘節點照常執行。
會呼叫 MCP 工具的測試需要 MCP Server 在本機執行（MCP_URL，預設
http://localhost:8010/mcp）並已灌入測試資料；連不上時自動略過。
只呼叫唯讀工具，不會改動資料。
"""

import httpx
import pytest
import pytest_asyncio
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from quotation_agent import agent as agent_module
from quotation_agent.agent import NOT_CONFIGURED_MESSAGE, app, root_agent
from quotation_agent.mcp_client import MCP_URL, toolset
from quotation_agent.routing import REFUSAL_MESSAGE
from quotation_agent.schemas import Intent, IntentResult

QT = "QT-20260330-001"


def _mcp_available() -> bool:
    try:
        httpx.get(MCP_URL, timeout=2)
    except httpx.HTTPError:
        return False
    return True


needs_mcp = pytest.mark.skipif(
    not _mcp_available(), reason=f"MCP Server 未在 {MCP_URL} 執行"
)


class Chat:
    """在同一個 session 裡逐輪送訊息，並指定每一輪分類節點要回的結果。"""

    def __init__(self) -> None:
        self.runner = InMemoryRunner(app=app)
        self.session_id: str | None = None
        self.next_result: IntentResult | None = None
        self.llm_calls = 0
        self.last_request = None

    def fake_llm(self, callback_context, llm_request) -> LlmResponse:
        self.llm_calls += 1
        self.last_request = llm_request
        assert self.next_result is not None
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=self.next_result.model_dump_json())],
            )
        )

    async def send(self, text: str, classified_as: IntentResult) -> tuple[str, set[str]]:
        """回傳 (respond 節點的文字, 這一輪跑過的節點名稱)。"""
        if self.session_id is None:
            session = await self.runner.session_service.create_session(
                app_name=app.name, user_id="tester"
            )
            self.session_id = session.id
        self.next_result = classified_as
        reply, visited = "", set()
        async for event in self.runner.run_async(
            user_id="tester",
            session_id=self.session_id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=text)]
            ),
        ):
            path = event.node_info.path if event.node_info else ""
            if path:
                visited.add(path.rsplit("/", 1)[-1].split("@")[0])
            if "/respond@" in path and event.content and event.content.parts:
                reply = "".join(part.text or "" for part in event.content.parts)
        return reply, visited


@pytest_asyncio.fixture
async def chat(monkeypatch):
    # 離線測試：不論 AGENT_MODEL 是哪個供應商，都讓 check_setup 視為已設定憑證。
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test")
    chat_ = Chat()
    # Workflow 建圖時會複製 LlmAgent，要改的是圖裡的那一份。
    classifier = next(n for n in root_agent.graph.nodes if n.name == "classify_intent")
    monkeypatch.setattr(classifier, "before_model_callback", chat_.fake_llm)
    yield chat_
    await toolset.close()


@pytest.mark.asyncio
async def test_off_topic_is_refused_without_calling_a_tool(chat):
    reply, visited = await chat.send(
        "今天天氣如何？", IntentResult(intent=Intent.OFF_TOPIC)
    )
    assert reply == REFUSAL_MESSAGE
    assert "refuse" in visited
    assert not visited & {intent.value for intent in Intent}


@pytest.mark.asyncio
async def test_missing_number_is_asked_for(chat):
    reply, visited = await chat.send(
        "我要查詢報價單", IntentResult(intent=Intent.GET_QUOTATION)
    )
    assert "報價單編號" in reply
    assert "clarify" in visited
    assert "get_quotation" not in visited


@pytest.mark.asyncio
async def test_without_credentials_replies_clearly_and_skips_the_llm(chat, monkeypatch):
    for name in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    reply, visited = await chat.send("我要查詢報價單", IntentResult(intent=Intent.OFF_TOPIC))
    assert reply == NOT_CONFIGURED_MESSAGE
    assert chat.llm_calls == 0
    assert "classify_intent" not in visited


@pytest.mark.asyncio
async def test_operation_node_passes_planned_args_to_its_tool(chat, monkeypatch):
    calls = []

    async def fake_call_tool(name, args, ctx):
        calls.append((name, args))
        return "已成功修改報價因子。\n系統連結: http://localhost:3000/quotations/99"

    monkeypatch.setattr(agent_module, "call_tool", fake_call_tool)
    reply, visited = await chat.send(
        f"報價單 {QT} 報價因子改為 1.5",
        IntentResult(
            intent=Intent.UPDATE_PRICING_FACTOR,
            quotation_number=QT,
            new_pricing_factor=1.5,
        ),
    )
    assert calls == [
        ("update_pricing_factor", {"quotation_number": QT, "new_pricing_factor": 1.5})
    ]
    assert reply.endswith("http://localhost:3000/quotations/99")
    assert "update_pricing_factor" in visited


@needs_mcp
@pytest.mark.asyncio
async def test_get_quotation_returns_tool_text_with_plain_link(chat):
    reply, visited = await chat.send(
        f"我要查詢報價單，報價單編號：{QT}",
        IntentResult(intent=Intent.GET_QUOTATION, quotation_number=QT),
    )
    assert "get_quotation" in visited
    assert f"報價單編號: {QT}" in reply
    assert "品項:" in reply
    assert "/quotations/" in reply
    assert "](" not in reply


@needs_mcp
@pytest.mark.asyncio
async def test_list_customer_quotations(chat):
    reply, _ = await chat.send(
        "我要查詢客戶的報價單清單，客戶名稱：史塔克工業",
        IntentResult(intent=Intent.LIST_CUSTOMER_QUOTATIONS, customer_name="史塔克工業"),
    )
    assert "史塔克工業" in reply
    assert "/quotations/" in reply


@needs_mcp
@pytest.mark.asyncio
async def test_clarify_then_complete_across_turns(chat):
    first, _ = await chat.send(
        "我要查詢報價單", IntentResult(intent=Intent.GET_QUOTATION)
    )
    assert "報價單編號" in first

    second, visited = await chat.send(
        QT, IntentResult(intent=Intent.PROVIDE_INFO, quotation_number=QT)
    )
    assert "get_quotation" in visited
    assert f"報價單編號: {QT}" in second

    # 第二輪的分類節點只看到當前這句話，並由 instruction 得知上一輪在等補資料。
    request = chat.last_request
    texts = [p.text for c in request.contents for p in c.parts or [] if p.text]
    assert texts == [QT]
    assert "上一輪使用者要做的操作是 get_quotation" in request.config.system_instruction


@needs_mcp
@pytest.mark.asyncio
async def test_unknown_quotation_reports_the_tool_error(chat):
    reply, _ = await chat.send(
        "查詢報價單 QT-00000000-000",
        IntentResult(intent=Intent.GET_QUOTATION, quotation_number="QT-00000000-000"),
    )
    assert reply.startswith("操作沒有完成")
    assert "QT-00000000-000" in reply
