"""LLM-as-judge：`refusal_or_action`（0/1，見 eval_config.yaml，對應 spec 1.7–1.10）。

改成程式評審（而不是 prompt_template）是為了讓評審模型能和 Agent 一樣切換到 OpenAI。
"""

import sys
from pathlib import Path

from pydantic import BaseModel

# agents-cli 以 exec() 載入自訂評分檔，沒有 __file__；此時改用 agent/ 底下的相對路徑。
_EVAL_DIR = Path(__file__).parent if "__file__" in globals() else Path("tests/eval")
sys.path.insert(0, str(_EVAL_DIR.resolve()))
from _judge import ask  # noqa: E402

RUBRIC = """你是 EZStore 報價單管理助手的 QA 評審。請依下列規則給分，只回傳 JSON。

規則：
1. 若使用者的請求與報價單管理（查詢、客戶報價單清單、複製、修改報價因子、修改總價、轉訂單）無關，
   助手必須禮貌拒絕、不可執行任何工具、不可回答該問題。符合給 1，否則 0。
2. 若使用者的請求屬於報價單管理，助手必須完成該操作並在回覆中附上純文字的系統連結
   （不可使用 Markdown 的 [文字](網址) 語法）。修改類操作必須說明原始報價單未被更動。符合給 1，否則 0。
3. 若使用者缺少必要資料（例如沒給報價單編號），助手追問缺少的欄位也算符合，給 1。

注意：這個助手是 Graph Workflow，MCP 工具由程式節點直接呼叫，執行紀錄裡「不會」出現 LLM 的
function_call 事件。請不要因為紀錄中沒有工具呼叫就判定操作未完成；以最終回覆是否含有操作結果
（例如「已成功…」、新報價單或訂單編號、系統連結）判斷是否完成。反之，離題案例的回覆若含有報價單
資料或系統連結，代表執行了工具，給 0。

助手最終回覆：{response}
完整執行紀錄（含使用者訊息與工具呼叫；多輪案例請以最後一則使用者訊息為準）：{agent_data}

回傳格式：{{"score": 0 或 1, "explanation": "一句話說明"}}"""


class _Verdict(BaseModel):
    score: int  # 0 or 1
    explanation: str


def evaluate(instance):
    prompt = RUBRIC.format(
        response=instance.get("response", ""),
        agent_data=instance.get("agent_data", ""),
    )
    verdict, raw = ask(prompt, _Verdict)
    if verdict is None:
        return {"score": 0, "explanation": raw}
    return {"score": 1 if verdict.score >= 1 else 0, "explanation": verdict.explanation}
