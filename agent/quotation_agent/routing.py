"""路由決策：純程式邏輯，不呼叫 LLM，也不碰 ADK。

意圖分類節點只負責把一句話轉成 `IntentResult`；要呼叫哪個工具、帶哪些參數、
要不要追問或拒答，全部在這裡決定。
"""

from .schemas import Intent, IntentResult, Pending, Plan

ROUTE_CLARIFY = "clarify"
ROUTE_REFUSE = "refuse"

# 每個操作對應的 MCP 工具必填參數。新增操作時在這裡加一筆。
REQUIRED_ARGS: dict[Intent, tuple[str, ...]] = {
    Intent.GET_QUOTATION: ("quotation_number",),
    Intent.LIST_CUSTOMER_QUOTATIONS: ("customer_name",),
    Intent.DUPLICATE_QUOTATION: ("quotation_number",),
    Intent.UPDATE_PRICING_FACTOR: ("quotation_number", "new_pricing_factor"),
    Intent.ADJUST_TOTAL_PRICE: ("quotation_number", "target_total_price"),
    Intent.CONVERT_TO_ORDER: ("quotation_number",),
}

ARG_LABELS: dict[str, str] = {
    "quotation_number": "報價單編號（例如 QT-20260330-001）",
    "customer_name": "客戶名稱（例如 史塔克工業）",
    "new_pricing_factor": "新的報價因子（例如 1.5）",
    "target_total_price": "目標總價（例如 8000）",
}

INTENT_LABELS: dict[Intent, str] = {
    Intent.GET_QUOTATION: "查詢報價單",
    Intent.LIST_CUSTOMER_QUOTATIONS: "查詢客戶的報價單清單",
    Intent.DUPLICATE_QUOTATION: "複製報價單",
    Intent.UPDATE_PRICING_FACTOR: "修改報價單報價因子",
    Intent.ADJUST_TOTAL_PRICE: "修改報價單總價",
    Intent.CONVERT_TO_ORDER: "報價單轉訂單",
}


def _extracted_args(result: IntentResult) -> dict[str, str | float]:
    args: dict[str, str | float] = {}
    for name in ARG_LABELS:
        value = getattr(result, name)
        if isinstance(value, str):
            value = value.strip()
        if value not in (None, ""):
            args[name] = value
    return args


def plan(result: IntentResult, pending: Pending | None) -> tuple[Plan, Pending | None]:
    """依分類結果與上一輪未完成的操作，決定路由。

    回傳 (本輪的 Plan, 要寫回 state 的 Pending)。
    """
    extracted = _extracted_args(result)

    if result.intent in REQUIRED_ARGS:
        intent = result.intent
        # 上一輪追問的是同一個操作（或只給了資料還沒說要做什麼）才沿用舊參數。
        carried = pending.args if pending and pending.intent in (None, intent) else {}
        args = {**carried, **extracted}
    elif result.intent is Intent.PROVIDE_INFO and (pending or extracted):
        intent = pending.intent if pending else None
        args = {**(pending.args if pending else {}), **extracted}
    else:
        # off_topic，或沒有任何可接續內容的 provide_info：一律拒答並清掉未完成的操作。
        return Plan(route=ROUTE_REFUSE), None

    if intent is None:
        return (
            Plan(route=ROUTE_CLARIFY, args=args, missing=["operation"]),
            Pending(intent=None, args=args),
        )

    required = REQUIRED_ARGS[intent]
    missing = [name for name in required if name not in args]
    if missing:
        return (
            Plan(route=ROUTE_CLARIFY, intent=intent, args=args, missing=missing),
            Pending(intent=intent, args=args),
        )

    tool_args = {name: args[name] for name in required}
    return Plan(route=intent.value, intent=intent, args=tool_args), None


def clarify_message(plan_: Plan) -> str:
    """追問缺少的欄位。"""
    if plan_.intent is None:
        operations = "、".join(INTENT_LABELS.values())
        return f"請問您要對報價單進行哪一項操作？我可以協助：{operations}。"
    fields = "、".join(ARG_LABELS[name] for name in plan_.missing)
    return f"要{INTENT_LABELS[plan_.intent]}，還需要您提供：{fields}。"


REFUSAL_MESSAGE = (
    "很抱歉，我只能處理報價單相關的操作："
    + "、".join(INTENT_LABELS.values())
    + "。其他需求（例如天氣、閒聊，或客戶與產品的新增修改）無法協助。"
)
