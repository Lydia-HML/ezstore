# ezstore-agent：報價單管理 Agent

以 Google ADK 2.x 的 Graph Workflow（`google.adk.workflow.Workflow`）建成的報價單管理助手，
透過 MCP Server 操作 EZStore 後端。ADK app 名稱為 `quotation_agent`（前端 Chat UI 依此呼叫）。
專案骨架由 `agents-cli scaffold create` 產生。

## 圖的設計

```
START → check_setup ──（沒有模型憑證）──────────────────────────────────┐
          │                                                              │
          └→ classify_intent（LLM）→ route_intent ─┬→ get_quotation ─────┤
                                                   ├→ list_customer_quotations
                                                   ├→ duplicate_quotation
                                                   ├→ update_pricing_factor
                                                   ├→ adjust_total_price
                                                   ├→ convert_to_order ──┤
                                                   ├→ clarify ───────────┤
                                                   └→ refuse ────────────┴→ respond
```

| 節點 | 檔案 | 做什麼 |
|------|------|--------|
| `check_setup` | `agent.py` | 沒有模型憑證就直接走到 `respond` 回覆錯誤（不呼叫 LLM）；把上一輪對話放進 state 給分類節點參考 |
| `classify_intent` | `agent.py` | **唯一的 LLM 節點**。`output_schema=IntentResult`，只輸出意圖與抽出的欄位，不回答問題 |
| `route_intent` | `agent.py` → `routing.py` | 純程式：決定要走哪個操作、工具參數、要追問或拒答；維護 `state.pending`（等待補資料的操作） |
| 6 個操作節點 | `agent.py`（`_operation`） | 各以 `route_intent` 決定好的參數呼叫**同名**的 MCP 工具（`mcp_client.call_tool`） |
| `clarify` | `routing.clarify_message` | 列出還缺的欄位 |
| `refuse` | `routing.REFUSAL_MESSAGE` | 固定拒答文字。離題由程式決定，不靠提示詞 |
| `respond` | `agent.py` | Chat UI 只顯示這個節點輸出的文字；工具回傳的文字原樣呈現 |

設計重點：

- **LLM 只做分類。** 工具選擇與參數完全由 `routing.py` 決定，所以可以用單元測試涵蓋（`tests/unit/test_routing.py`），整合測試也能用假的分類結果跑整張圖（`tests/integration/test_workflow.py`）。
- **追問後接續。** 缺欄位時把操作與已知參數存進 `state.pending`；下一句只補資料時（分類為 `provide_info`）合併後再執行。若 session 是由既有紀錄接續、沒有 `pending`，分類節點會從 `check_setup` 提供的上一輪對話推回原本的操作。
- **模型可替換。** `llm.py` 依 `AGENT_MODEL` 選擇供應商：`gemini-*` 走 Gemini（AI Studio 或 Vertex AI），`openai/<模型>` 經 LiteLLM 走 OpenAI。

## 如何新增一個操作

假設 MCP Server 新增了工具 `cancel_quotation(quotation_number)`：

1. **`quotation_agent/schemas.py`**：在 `Intent` 加上 `CANCEL_QUOTATION = "cancel_quotation"`（值必須與 MCP 工具同名）。若需要新欄位，也加到 `IntentResult`。
2. **`quotation_agent/routing.py`**：在 `REQUIRED_ARGS` 加 `Intent.CANCEL_QUOTATION: ("quotation_number",)`，在 `INTENT_LABELS` 加中文名稱（拒答與追問訊息會自動列出）；新欄位要加到 `ARG_LABELS`。
3. **`quotation_agent/agent.py`**：
   - `cancel_quotation = _operation(Intent.CANCEL_QUOTATION)`，並加進 `OPERATIONS`（邊會自動接上 `route_intent` 與 `respond`）。
   - 在 `CLASSIFY_INSTRUCTION` 的意圖清單加一行說明，並把它從 `off_topic` 的描述中移除（如果原本列在那裡）。
4. **測試**：在 `tests/unit/test_routing.py` 加路由案例；在 `tests/eval/datasets/quotation-actions.json` 加一個 `eval_case_id` 為 `cancel_quotation` 的案例。

## 開發指令

```bash
uv sync --group dev
uv run python scripts/mcp_call.py                       # 列出 MCP 工具（MCP_URL 預設 http://localhost:8010/mcp）
agents-cli playground --port 8501                       # 本機網頁測試（8080 已被 backend 佔用）
uv run pytest tests/unit tests/integration -q           # 單元與離線整合測試
GOOGLE_CLOUD_PROJECT=local-only agents-cli eval run --dataset tests/eval/datasets/quotation-actions.json
GOOGLE_CLOUD_PROJECT=local-only agents-cli eval run --dataset tests/eval/datasets/quotation-guardrails.json
```

環境變數見 `.env.example`；沒有 `agent/.env` 時會改讀專案根目錄的 `.env`。
Eval 指標（`tests/eval/eval_config.yaml`）：`custom_response_quality`、`link_present`、`refusal_or_action`、`agent_turn_count`。
