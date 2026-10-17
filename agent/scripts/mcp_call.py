"""直接呼叫 EZStore MCP Server 的工具（開發除錯用，不經過 Agent）。

用法（在 agent/ 目錄）：
    uv run python scripts/mcp_call.py                      # 列出工具
    uv run python scripts/mcp_call.py get_quotation quotation_number=QT-20260330-001
"""

import asyncio
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_URL = os.environ.get("MCP_URL", "http://localhost:8010/mcp")


def _parse(pairs: list[str]) -> dict[str, str | float]:
    args: dict[str, str | float] = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        try:
            args[key] = float(value)
        except ValueError:
            args[key] = value
    return args


async def main(argv: list[str]) -> None:
    async with streamable_http_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            if not argv:
                for tool in (await session.list_tools()).tools:
                    print(f"- {tool.name}: {(tool.description or '').splitlines()[0]}")
                return
            result = await session.call_tool(argv[0], _parse(argv[1:]))
            for item in result.content:
                if getattr(item, "type", "") == "text":
                    print(item.text)
            if result.is_error:
                sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
