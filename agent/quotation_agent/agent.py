"""EZStore 報價單管理 Agent：以 ADK Graph Workflow 建成的明確流程圖。

    START → check_setup → classify_intent(LLM) → route_intent ─┬→ 六個操作節點 ─┐
                 │                                             ├→ clarify ──────┼→ respond
                 │                                             └→ refuse ───────┤
                 └─────────────（沒有模型憑證）───────────────────────────────────┘

只有 classify_intent 呼叫 LLM；工具的選擇與參數由 route_intent 以程式決定。
"""

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.workflow import Workflow, node
from google.genai import types

# 本機開發：先讀 agent/.env，再以專案根目錄的 .env 補上沒設定的值。容器內由 Compose 注入。
_AGENT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_AGENT_ROOT / ".env")
load_dotenv(_AGENT_ROOT.parent / ".env")

from .llm import (  # noqa: E402
    build_model,
    has_credentials,
    missing_credentials_message,
    model_name,
)
from .mcp_client import call_tool  # noqa: E402
from .routing import (  # noqa: E402
    REFUSAL_MESSAGE,
    ROUTE_CLARIFY,
    ROUTE_REFUSE,
    clarify_message,
    plan,
    previous_exchange,
)
from .schemas import Intent, IntentResult, Pending, Plan  # noqa: E402

MODEL = model_name()

ROUTE_READY = "ready"
ROUTE_NOT_CONFIGURED = "not_configured"

NOT_CONFIGURED_MESSAGE = missing_credentials_message(MODEL)

CLASSIFY_INSTRUCTION = """你是 EZStore 報價單管理系統的意圖分類器。你不回答問題，只把使用者的訊息分類並抽出欄位。

intent 只能是下列其中一個：
- get_quotation：查詢某一張報價單的內容或品項
- list_customer_quotations：查詢某個客戶的報價單清單
- duplicate_quotation：複製報價單
- update_pricing_factor：修改報價單的報價因子
- adjust_total_price：修改報價單的總價
- convert_to_order：把報價單轉成訂單
- provide_info：訊息只提供了資料（報價單編號、客戶名稱、數字），沒有說要做什麼操作
- off_topic：其他所有需求，包含天氣、閒聊、新增或修改客戶、新增或修改產品、刪除資料、訂單查詢等

規則：
- 欄位只填使用者在這則訊息裡明確寫出的值，沒寫的一律留空，不可猜測或補值。
- 報價單編號原樣抄寫（例如 QT-20260330-001）。
- 使用者說要做某個操作但沒給編號或數值時，intent 仍填該操作，欄位留空。
- 若下方提供了上一輪對話，而這則訊息只是在回答助手的追問（例如只給了報價單編號或數值），
  intent 填上一輪使用者要做的操作，欄位可合併上一輪使用者明確寫出的值；其他情況只看這則訊息。
{previous_exchange?}{pending_hint?}"""


def _event_text(event: Event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(part.text or "" for part in event.content.parts if not part.thought)


def _text(node_input: Any) -> str:
    if isinstance(node_input, types.Content):
        return "".join(part.text or "" for part in node_input.parts or [])
    return str(node_input)


def check_setup(ctx: Context, node_input: types.Content):
    """沒有模型憑證時直接回覆清楚的錯誤訊息，不進 LLM 節點。

    同時把上一輪的「使用者訊息／助手回覆」放進 state，讓分類節點在追問後能接續。
    只靠 state 裡的 pending 不夠：session 若是由既有對話紀錄接續（例如 eval 的多輪案例），
    pending 不存在，但對話紀錄還在。
    """
    if not has_credentials(MODEL):
        return Event(output=NOT_CONFIGURED_MESSAGE, route=ROUTE_NOT_CONFIGURED)
    exchange = previous_exchange(
        [(event.author, _event_text(event)) for event in ctx.session.events]
    )
    return Event(
        output=_text(node_input),
        route=ROUTE_READY,
        state={"previous_exchange": exchange},
    )


classify_intent = LlmAgent(
    name="classify_intent",
    model=build_model(MODEL),
    instruction=CLASSIFY_INSTRUCTION,
    # 每輪只看當前這句話；跨輪的接續由 route_intent 用 state 裡的 pending 處理。
    include_contents="none",
    output_schema=IntentResult,
    generate_content_config=types.GenerateContentConfig(temperature=0),
)


def route_intent(ctx: Context, node_input: IntentResult):
    """路由節點：決定走哪個操作、追問或拒答，並維護未完成的操作。"""
    raw_pending = ctx.state.get("pending")
    pending = Pending.model_validate(raw_pending) if raw_pending else None
    plan_, next_pending = plan(node_input, pending)

    hint = ""
    if next_pending and next_pending.intent:
        hint = (
            f"\n補充：上一輪使用者要做的操作是 {next_pending.intent.value}，系統正在等他補資料。"
            "如果這則訊息只是補資料，intent 填 provide_info。"
        )
    return Event(
        output=plan_,
        route=plan_.route,
        state={
            "pending": next_pending.model_dump(mode="json") if next_pending else None,
            "pending_hint": hint,
        },
    )


def _operation(intent: Intent):
    """建立一個操作節點：以路由節點決定好的參數呼叫同名的 MCP 工具。"""

    @node(name=intent.value)
    async def run(ctx: Context, node_input: Plan) -> str:
        return await call_tool(intent.value, node_input.args, ctx)

    return run


get_quotation = _operation(Intent.GET_QUOTATION)
list_customer_quotations = _operation(Intent.LIST_CUSTOMER_QUOTATIONS)
duplicate_quotation = _operation(Intent.DUPLICATE_QUOTATION)
update_pricing_factor = _operation(Intent.UPDATE_PRICING_FACTOR)
adjust_total_price = _operation(Intent.ADJUST_TOTAL_PRICE)
convert_to_order = _operation(Intent.CONVERT_TO_ORDER)

OPERATIONS = (
    get_quotation,
    list_customer_quotations,
    duplicate_quotation,
    update_pricing_factor,
    adjust_total_price,
    convert_to_order,
)


def clarify(node_input: Plan) -> str:
    """追問節點：列出還缺的欄位。"""
    return clarify_message(node_input)


def refuse(node_input: Plan) -> str:
    """拒答節點：固定文字，不經過 LLM。"""
    return REFUSAL_MESSAGE


def respond(node_input: str):
    """回覆節點：Chat UI 只顯示這個節點輸出的文字。工具回傳的文字原樣呈現。"""
    yield Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=node_input)])
    )
    yield Event(output=node_input)


root_agent = Workflow(
    # Keep in sync with agents-cli-manifest.yaml (create_params.root_agent_name).
    name="quotation_agent",
    description="EZStore 報價單管理助理：查詢、複製、調價與轉訂單。",
    edges=[
        ("START", check_setup),
        (check_setup, {ROUTE_READY: classify_intent, ROUTE_NOT_CONFIGURED: respond}),
        (classify_intent, route_intent),
        (
            route_intent,
            {
                **{op.name: op for op in OPERATIONS},
                ROUTE_CLARIFY: clarify,
                ROUTE_REFUSE: refuse,
            },
        ),
        *[(op, respond) for op in OPERATIONS],
        (clarify, respond),
        (refuse, respond),
    ],
)

app = App(
    root_agent=root_agent,
    name="quotation_agent",
)
