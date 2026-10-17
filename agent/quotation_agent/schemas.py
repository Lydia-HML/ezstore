"""Workflow 節點之間傳遞的資料結構。"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Intent(StrEnum):
    """意圖分類節點可以輸出的類別。

    前六個值與 MCP Server 的工具同名；後兩個不對應任何工具。
    """

    GET_QUOTATION = "get_quotation"
    LIST_CUSTOMER_QUOTATIONS = "list_customer_quotations"
    DUPLICATE_QUOTATION = "duplicate_quotation"
    UPDATE_PRICING_FACTOR = "update_pricing_factor"
    ADJUST_TOTAL_PRICE = "adjust_total_price"
    CONVERT_TO_ORDER = "convert_to_order"
    PROVIDE_INFO = "provide_info"
    OFF_TOPIC = "off_topic"


class IntentResult(BaseModel):
    """意圖分類節點（LLM）的結構化輸出。"""

    intent: Intent = Field(description="使用者這句話的意圖類別")
    quotation_number: str | None = Field(
        default=None, description="報價單編號，例如 QT-20260330-001；沒提到就留空"
    )
    customer_name: str | None = Field(
        default=None, description="客戶名稱，例如 史塔克工業；沒提到就留空"
    )
    new_pricing_factor: float | None = Field(
        default=None, description="要改成的報價因子數值；沒提到就留空"
    )
    target_total_price: float | None = Field(
        default=None, description="要改成的目標總價數值；沒提到就留空"
    )


class Pending(BaseModel):
    """追問後存在 session state 的未完成操作，下一輪用來接續。"""

    intent: Intent | None = None
    args: dict[str, str | float] = Field(default_factory=dict)


class Plan(BaseModel):
    """路由節點的輸出：要走哪條邊、帶哪些工具參數。"""

    route: str
    intent: Intent | None = None
    args: dict[str, str | float] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
