"""透過 ADK 的 McpToolset 連接 EZStore MCP Server（Streamable HTTP）。

Workflow 的操作節點直接用工具名稱呼叫，不經過 LLM 的 function calling。
"""

import os
from typing import Any

from google.adk.agents.context import Context
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

MCP_URL = os.environ.get("MCP_URL", "http://localhost:8010/mcp")

toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(url=MCP_URL),
)


def _result_text(result: Any) -> tuple[str, bool]:
    """把 MCP 工具回傳值轉成 (文字, 是否為錯誤)。"""
    if not isinstance(result, dict):
        return str(result), False
    if result.get("error"):
        return str(result["error"]), True
    parts = [
        item.get("text", "")
        for item in result.get("content") or []
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p), bool(result.get("isError"))


async def call_tool(name: str, args: dict[str, Any], ctx: Context) -> str:
    """呼叫一個 MCP 工具並回傳它的文字內容；失敗時回傳可直接給使用者看的訊息。"""
    try:
        tools = {tool.name: tool for tool in await toolset.get_tools()}
        text, is_error = _result_text(
            await tools[name].run_async(args=args, tool_context=ctx)
        )
    except Exception as e:  # MCP Server 連不上、工具不存在等
        return f"目前無法連線報價單系統（MCP Server：{MCP_URL}），請稍後再試。\n錯誤：{e}"
    if is_error:
        return f"操作沒有完成：{text}"
    return text
