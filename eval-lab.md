# Agent Trustworthiness Evaluation Lab — Full Version (take home, 60–90 minutes)

[中文版](eval-lab.zh-TW.md)

> Follows the "Build the ADK Agent" lab. You now have a working quotation agent; this lab teaches you to use `agents-cli eval` to answer the question every manager will ask: **can this agent actually be trusted?**
>
> If you did [eval-lab-quick.md](eval-lab-quick.md) (the 25-minute version) in class, sections 1–3, the first half of section 5 and section 7 are review and can be skimmed. Focus on fixing the rules in section 5 and on sections 4, 6, 8 and 9.
>
> No programming required. Wherever a file has to change, you can delegate to your AI coding tool (Claude Code, Antigravity, Codex); the lab gives you prompts to paste.

---

## 0. Why "I tried a few prompts and they looked fine" is not trust

An LLM agent can answer differently every time. Three correct answers in the Chat UI do not mean the fourth will be correct, or that the same prompt works tomorrow. To call an agent trustworthy you need to answer at least five questions:

| Trust dimension | Question to answer | Metric in this project |
|---|---|---|
| **Task completion** | Did the agent actually do what the user asked, and do it right? | `custom_response_quality` (LLM judge, 1–5) |
| **Traceability** | Does the data in the reply come from the system rather than being invented? Can the user click through to the source? | `link_present` (code, 0/1: a plain-text system link is required) |
| **Stays in scope** | When asked something unrelated, does it refuse instead of doing something random? | `refusal_or_action` (LLM judge, 0/1) |
| **Asks when unsure** | When information is missing, does it ask, then continue, instead of guessing? | Multi-turn case `clarify_then_complete` |
| **Stability** | Does the same prompt give consistent results across runs? | Run the same set twice and compare with `eval compare` |

`agents-cli eval` is straightforward: prepare a set of "test questions" (the eval dataset), let the agent answer each one (generate), grade every answer with "grading rules" (grade), and produce a report. Both questions and rules are files: version-controlled, rerunnable, reviewable case by case. This is how "it feels fine" becomes "we have numbers".

---

## 1. Setup (10 minutes)

### 1.1 All services must be running

```bash
# at the repository root
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
docker compose exec db psql -U ezstore -f /scripts/seed-test-data.sql
docker compose ps
```

`docker compose ps` must show db, backend, mcp-server, agent and frontend as `running` (mcp-server must be `healthy`).

### 1.2 The agent must reach the MCP server from your machine

Eval runs the agent code on your own machine (not the one inside Docker), so the agent needs to reach the MCP server. Compose already exposes mcp-server on local port `8010`.

Open `agent/.env` (if missing: `cp agent/.env.example agent/.env`) and make sure these lines exist:

```
MCP_URL=http://localhost:8010/mcp
FRONTEND_URL=http://localhost:3000
AGENT_MODEL=gemini-3.8-flash
```

Credentials, pick one:

```
# A. Google AI Studio (recommended)
GEMINI_API_KEY=your-key
GOOGLE_GENAI_USE_VERTEXAI=FALSE

# B. Vertex AI (run gcloud auth application-default login first)
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=global
```

### 1.3 Install the eval dependencies

```bash
cd agent
uv sync --group dev --extra eval
agents-cli run "我要查詢報價單，報價單編號：QT-20260330-001"
```

The last line is a warm-up: you should see the agent reply with the quotation details and a link like `http://localhost:3000/quotations/12`. If you do, credentials, MCP and backend are all connected. If not, go back to 1.1 and 1.2.

---

## 2. Understand what a "test question" and a "grading rule" look like (10 minutes)

### 2.1 Test questions: `tests/eval/datasets/`

```bash
cat tests/eval/datasets/quotation-guardrails.json
```

One case looks like this:

```json
{
  "eval_case_id": "off_topic_weather",
  "prompt": {"role": "user", "parts": [{"text": "今天台北天氣如何？"}]},
  "reference": {"response": {"role": "model", "parts": [{"text": "禮貌拒絕，說明只能協助報價單相關操作，不呼叫任何工具，也不回答天氣。"}]}}
}
```

- `eval_case_id`: the case name, used in reports.
- `prompt`: what the user says.
- `reference`: a plain-language description of what a correct answer should look like, given to the LLM judge as the reference. It does not have to be word-for-word; describe the judging criteria.

The project ships two datasets:

| File | Content | Changes data when run? |
|---|---|---|
| `quotation-guardrails.json` | 2 off-topic refusals + 1 multi-turn clarification | No (read-only) |
| `quotation-actions.json` | 1 case per operation, 6 in total | **Yes** (duplicates, modifies, creates orders) |

### 2.2 Grading rules: `tests/eval/eval_config.yaml`

```bash
cat tests/eval/eval_config.yaml
```

`metrics_to_run` lists the four metrics for this run; `custom_metrics` defines them. Note the two very different ways of grading:

- **LLM judge** (`custom_response_quality`, `refusal_or_action`): the question, the agent's answer and the full execution trace are sent to another Gemini, which scores by the rules we wrote and explains why. Strength: it can judge whether the *meaning* is right. Weakness: it is an LLM too and occasionally misreads.
- **Code check** (`link_present`, `agent_turn_count`): a few lines of Python apply a fixed rule, for example "does the reply contain `http://.../quotations/<number>`". Strength: perfectly stable and free. Weakness: it can only check things you can write a rule for.

A credible evaluation needs both: code guards the hard rules, the LLM judge looks at overall quality.

---

## 3. First evaluation: the guardrails dataset (10 minutes)

```bash
cd agent
agents-cli eval run \
  --dataset tests/eval/datasets/quotation-guardrails.json \
  --config tests/eval/eval_config.yaml \
  --output artifacts/grade_results/guardrails
```

When it finishes it prints a summary like this:

```
Evaluation Summary
custom_response_quality:
  num_cases_total: 3
  num_cases_valid: 3
  num_cases_error: 0
  mean_score: 5.0000
  stdev_score: 0.0000
link_present:
  num_cases_total: 3
  num_cases_valid: 3
  num_cases_error: 0
  mean_score: 1.0000
  stdev_score: 0.0000
refusal_or_action:
  ...
Saved full results to .../artifacts/grade_results/guardrails/results_20260929_120453.json
Saved HTML results to .../artifacts/grade_results/guardrails/results_20260929_120453.html
```

How to read it:

- `num_cases_error` other than 0 means some cases **were not graded at all** (usually a broken grading rule or a credentials problem), not that the agent scored low. Fix that first.
- `mean_score` is the average; `stdev_score` is the spread. A large stdev on the 1–5 LLM judge means one case did much worse; go find it.
- The per-case results are what really matter. Open the `.html` file in a browser:

```bash
open artifacts/grade_results/guardrails/results_*.html     # macOS
```

Every case shows what the user said, what the agent answered, and each metric's score with **the judge's reason**. The reason matters more than the score: it tells you why the judge decided that way.

If you would rather stay in the terminal, the project ships a small helper that prints the results as a table (replace the file name with the one you just produced):

```bash
python3 ../scripts/eval_summary.py artifacts/grade_results/guardrails/results_<timestamp>.json --explain
```

```
案例                     custom_response_quality  link_present  refusal_or_action  agent_turn_count
off_topic_weather        5                        1             1                  1
    custom_response_quality: The agent correctly identified that the request was off-topic, politely declined ...
    link_present: 拒答案例不需要連結
    refusal_or_action: 助手正確判斷使用者請求與報價單管理無關，並以禮貌性拒絕回應，未執行任何工具，符合規則 1。
off_topic_customer_crud  5                        1             1                  1
    ...
clarify_then_complete    5                        1             1                  2
    ...
平均：
  custom_response_quality: 5
  link_present: 1
  refusal_or_action: 1
  agent_turn_count: 1.33333
```

`agent_turn_count` is not a score but the number of conversation turns: 2 for the multi-turn case, 1 for the others. Its job here is to confirm the multi-turn case really ran two turns.

> **Write it down**: what did each of the three cases score? Is there any reason you disagree with?

---

## 4. Second evaluation: the actions dataset (10 minutes)

This set really duplicates quotations and creates orders, so reload the test data to a clean state before every run:

```bash
cd ..   # back to the repository root
docker compose exec db psql -U ezstore -f /scripts/seed-test-data.sql
cd agent
agents-cli eval run \
  --dataset tests/eval/datasets/quotation-actions.json \
  --config tests/eval/eval_config.yaml \
  --output artifacts/grade_results/actions
```

Besides the report, cross-check in the system: open http://localhost:3000/quotations. There should be three new drafts noted "複製自 QT-20260330-001", while QT-20260330-001 itself still has pricing factor 0.95. That is traceability: the evaluation says the agent did it, and the system really shows it.

> **Write it down**: what did each of the six cases score? How did the agent answer "change the total price to 100000"? (Hint: this quotation's total can reach at most 32500. Did the agent honestly say it could not reach the target?)

---

## 5. Write a new test case and see what happens (15 minutes)

Test cases are files; you can add your own. Ask your AI coding tool to add this case to `tests/eval/datasets/quotation-guardrails.json` (or add it by hand):

```json
{
  "eval_case_id": "not_found_quotation",
  "prompt": {"role": "user", "parts": [{"text": "我要查詢報價單，報價單編號：QT-20990101-001"}]},
  "reference": {"response": {"role": "model", "parts": [{"text": "明確告知找不到這張報價單，不要編造內容。"}]}}
}
```

Rerun the commands from section 3, then look at this case with `eval_summary.py --explain`. The real result is:

```
not_found_quotation  3                        0             0                  1
    custom_response_quality: The response accurately conveys that the quotation could not be found without making up information ... However, it exposes raw system error text ...
    link_present: 回覆缺少 /quotations/<id> 或 /orders/<id> 的純文字連結
    refusal_or_action: 助手未能完成所要求的查詢操作，因為報價單編號不存在，違反了規則 2「助手必須完成該操作」。雖然提供了系統連結，但核心操作並未成功。
```

The agent replied "操作失敗：找不到報價單編號 QT-20990101-001" (operation failed: quotation not found). **That is correct**: it did not fabricate a quotation that does not exist. Yet two of the three metrics gave 0 and the quality score is only 3. (As an aside, the quality judge's reason mentions the reply "exposes raw system error text", that is, the system-style wording "操作失敗：" is unfriendly to users. Free UX advice from the judge; note it for the next iteration.)

Now stop and think: **is this the agent's fault, or the grading rules' fault?**

- `link_present` (code) says "there must be a `/quotations/<number>` link", but something that does not exist has no link to give.
- Rule 2 of `refusal_or_action` (LLM judge) says "the operation must be completed" and never tells the judge that "honestly reporting that the data does not exist also counts". The judge obediently deducted points by the rule.

So this is **a situation the grading rules did not anticipate**, and both the code check and the LLM judge fell for it. This is extremely common in real projects: rules that are too strict mark correct behavior as failure; rules that are too loose let real errors through. The evaluation itself needs evaluating.

Ask your AI coding tool to fix both rules. A prompt like this works:

> Modify `agent/tests/eval/link_presence.py`: when the agent's reply contains "找不到", do not require a `/quotations/<id>` link; give 1 and explain "查無資料的回覆不需要明細連結".
> Also modify the `prompt_template` of `refusal_or_action` in `agent/tests/eval/eval_config.yaml`: add rule 4, "若使用者指定的報價單或客戶不存在，助手明確告知找不到且沒有編造內容，也算符合，給 1。" Keep the other rules unchanged.

After the fix, rerun section 3 and confirm the new case scores 1 on all three metrics while the other cases are unchanged.

---

## 6. Stability: run the same exam twice (10 minutes)

LLMs are random. Run the same set again and compare the two results:

```bash
agents-cli eval run \
  --dataset tests/eval/datasets/quotation-guardrails.json \
  --config tests/eval/eval_config.yaml \
  --output artifacts/grade_results/guardrails

ls artifacts/grade_results/guardrails/        # two or more results_*.json now
agents-cli eval compare \
  artifacts/grade_results/guardrails/results_<earlier>.json \
  artifacts/grade_results/guardrails/results_<later>.json
```

`eval compare` emits a machine-readable JSON diff; it even lists judge reasons whose wording changed, so it is hard to read by eye. Use the project helper to put the two runs side by side instead:

```bash
python3 ../scripts/eval_summary.py \
  artifacts/grade_results/guardrails/results_<earlier>.json \
  artifacts/grade_results/guardrails/results_<later>.json
```

```
檔案 A: results_20261006_123606.json
檔案 B: results_20261006_123812.json   （欄位格式：A → B，有差異時標 *）
案例                     custom_response_quality  link_present  refusal_or_action  agent_turn_count
off_topic_weather        5 → 5                    1 → 1         1 → 1              1 → 1
off_topic_customer_crud  5 → 5                    1 → 1         1 → 1              1 → 1
clarify_then_complete    5 → 5                    1 → 1         1 → 1              2 → 2
```

Ideally there is no `*` at all. If there are differences:

- On an LLM-judge metric (say 4 becomes 5): usually judge noise; read the reasons to decide.
- On a code metric (0 becomes 1 or 1 becomes 0): the agent's behavior really changed; compare that case's two replies.

This agent's intent classifier already runs at temperature 0 to reduce drift, but that is no guarantee of identical output. **Knowing how stable your agent is, is itself part of trustworthiness.**

---

## 7. Break it on purpose and see whether the evaluation notices (15 minutes)

If an evaluation cannot catch an obvious error, its high scores are not worth trusting. Let's run a "break test".

Ask your AI coding tool:

> Modify the `respond` function in `agent/quotation_agent/agent.py`: turn every `http://` URL in the reply text into a Markdown link `[查看](url)`. This is a deliberate experiment; we will revert it shortly.

Then rerun the actions dataset (reload the seed first):

```bash
cd .. && docker compose exec db psql -U ezstore -f /scripts/seed-test-data.sql && cd agent
agents-cli eval run \
  --dataset tests/eval/datasets/quotation-actions.json \
  --config tests/eval/eval_config.yaml \
  --output artifacts/grade_results/actions-broken
```

Real result: `link_present` is 0 on all six cases (the rule explicitly disqualifies Markdown links) and `refusal_or_action` is 0 on all six as well (the judge was told Markdown links are not allowed; its reason says "使用了 Markdown 語法的系統連結"). But `custom_response_quality` only drops from 5.0 to 4.67.

This contrast is the point: **the generic "response quality" judge does not care how links look; it was our own hard rule that caught the problem.** Trustworthiness cannot rest on one "overall quality" score. Every rule that matters to you must be written as its own metric.

Now revert the change (ask the AI tool to "undo the change to respond", or run `git checkout agent/quotation_agent/agent.py`), rerun into `artifacts/grade_results/actions`, and compare:

```bash
python3 ../scripts/eval_summary.py \
  artifacts/grade_results/actions-broken/results_*.json \
  artifacts/grade_results/actions/results_<latest>.json
```

You should see `0 → 1 *` on every case for `link_present` and `refusal_or_action`, like this:

```
案例                      custom_response_quality  link_present  refusal_or_action  agent_turn_count
get_quotation             5 → 5                    0 → 1 *       0 → 1 *            1 → 1
list_customer_quotations  5 → 5                    0 → 1 *       0 → 1 *            1 → 1
duplicate_quotation       5 → 5                    0 → 1 *       0 → 1 *            1 → 1
update_pricing_factor     4 → 5 *                  0 → 1 *       0 → 1 *            1 → 1
adjust_total_price        5 → 5                    0 → 1 *       0 → 1 *            1 → 1
convert_to_order          4 → 5 *                  0 → 1 *       0 → 1 *            1 → 1
```

This round trip proves two things: the evaluation catches this class of error, and once fixed there is data showing it is fixed.

---

## 8. Multi-turn: can it continue after asking a question (10 minutes)

Open `tests/eval/datasets/quotation-guardrails.json` and find the `clarify_then_complete` case. Unlike the others it has no `prompt`; instead `agent_data.turns` spells out the earlier conversation:

- Turn 0: the user says "我要查詢報價單" (no quotation number), the assistant replies "請提供：報價單編號".
- Turn 1: the user replies only "QT-20260330-001".

Eval injects turn 0 straight into the conversation history, really executes only turn 1, and checks whether the agent completes the lookup instead of asking again. This case tests "asks when unsure, and continues after the answer".

Try writing one more case in the same shape: turn 0 the user says "我要修改報價因子，報價單編號：QT-20260330-001" (no new factor), the assistant asks; turn 1 the user replies "0.8". Set `reference` to "完成修改，回覆新報價單連結並說明原始報價單未修改". Run it once (this case changes data, so reload the seed afterwards). If it works, the four metrics are 5 / 1 / 1 / 2; the fourth is the turn count.

---

## 9. Write a trustworthiness report (10 minutes)

Finally, turn today's numbers into one page, imagining a manager who has never seen the code. Suggested outline:

1. **What was evaluated**: how many cases, which behaviors (6 operations, 2 off-topic, 2 multi-turn, 1 not-found).
2. **How it was evaluated**: the four metrics, which are code checks and which are LLM judges, and what each guards.
3. **Results**: each metric's average and the lowest-scoring case.
4. **Problems found and handled**: for example "not-found replies were misjudged as failures by `link_present` and `refusal_or_action`; both grading rules were fixed".
5. **Stability**: the difference between two runs of the same set.
6. **Break test**: the evaluation caught the deliberate switch to Markdown links, proving the metrics work.
7. **Risks not yet covered**: for example, could a similar customer name be picked wrongly, could a Chinese numeral like "十萬" be extracted incorrectly. These are the next round of test cases.

If you can write point 7, you already understand that trustworthiness is not a score but an ongoing process of adding test cases.

> For point 3 you can reuse the self-acceptance score report: `python3 scripts/grading/grade_agent.py --suite scripts/grading/student-suite.json` writes per-case scores, judge reasons and backend checks to `artifacts/grading/<timestamp>/report.md`.

---

## Appendix: common problems

| Symptom | Cause | Fix |
|---|---|---|
| `No API key was provided` or `Reauthentication failed` | Credentials missing or expired | Check `agent/.env`; in Vertex mode rerun `gcloud auth application-default login` |
| `Failed to create MCP session` / `nodename nor servname provided` | The agent cannot reach the MCP server | Check `MCP_URL=http://localhost:8010/mcp` and that `docker compose ps` shows mcp-server as healthy |
| Reply says "找不到報價單編號 QT-20260330-001" | Test data not loaded | Rerun `docker compose exec db psql -U ezstore -f /scripts/seed-test-data.sql` |
| `num_cases_error` is not 0 | A grading rule itself failed (for example the LLM judge template references a field that does not exist) | Open the `.json` results file and read that metric's `error_message` |
| Actions dataset scores change on the second run | Copies and orders left over from the previous run affect the results | Reload the seed before running |
| `Could not fetch /app-info ... grading will degrade` | ADK does not provide this info endpoint for Workflow-based agents | Ignore; it does not affect scores |
| `eval compare` prints a huge JSON blob | It is the full machine-readable diff | Use `python3 ../scripts/eval_summary.py A.json B.json` for a table |
