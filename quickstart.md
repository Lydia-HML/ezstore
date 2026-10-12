# Quick Start Guide

> EZStore - B2B Quotation & Order Management System (AI Agent development workshop)

[中文版](quickstart.zh-TW.md)

---

## 1. Before class (please finish before the workshop)

### 1.1 Required tools

| Tool | Purpose | Download |
|------|---------|----------|
| Docker Desktop | Starts the whole system with one command (database, backend, frontend, agent, MCP server) | https://www.docker.com/products/docker-desktop/ |
| uv | Python package and virtualenv manager, also installs agents-cli | https://docs.astral.sh/uv/getting-started/installation/ |
| google-agents-cli | Google's official agent development CLI (scaffold, playground, eval) | after installing uv: `uv tool install google-agents-cli` |
| An AI coding tool | One of Claude Code, Gemini CLI, Antigravity, Cursor, ... | see each tool's site |
| Google AI Studio API key | The Gemini model used by the agent (free tier is enough) | https://aistudio.google.com/apikey |

> If you only need to *run* the system, Docker is enough. Go, Bun and Node.js are only needed to change backend or frontend source code, or to run E2E tests locally.

### 1.2 Optional tools (local development / testing)

| Tool | Purpose | Download |
|------|---------|----------|
| Node.js + Bun | Frontend development and Playwright E2E | https://nodejs.org/ , https://bun.com/ |
| Go | Backend development | https://go.dev/dl/ |
| Playwright | Running E2E tests locally | https://playwright.dev/docs/intro |

### 1.3 Verify the installation

```bash
docker --version && docker compose version
uv --version
agents-cli --version
```

---

## 2. Get the project

### Step 0: Fork the repository

Fork this repository on GitHub: https://github.com/cshliu77/ezstore (keep "Copy the main branch only" checked)

### Step 1: Clone your forked repository

```bash
git clone https://github.com/<your-github-username>/ezstore.git
cd ezstore
```

### Step 2: Set the API key

```bash
cp .env.example .env
```

Open `.env` in an editor and put your Google AI Studio API key after `GEMINI_API_KEY=`. `.env` is never committed to Git.

> If you already have a GCP project you can use Vertex AI instead: run `gcloud auth application-default login` and set `GOOGLE_GENAI_USE_VERTEXAI=true` and `GOOGLE_CLOUD_PROJECT` in `.env`. For the workshop we recommend an AI Studio key; it needs no GCP billing.

---

## 3. Start the system

### Step 3: Start with prebuilt images (fastest)

```bash
docker compose up -d
```

### Step 4: Build from local source (after changing code)

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

### Step 5: Load the test data

```bash
docker compose exec db psql -U ezstore -f /scripts/seed-test-data.sql
```

### Step 6: Check the services

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| AI assistant (Chat UI) | http://localhost:3000/agent |
| Backend API | http://localhost:8080/api/v1 |
| Swagger UI | http://localhost:8080/swagger/index.html |
| Health check | http://localhost:8080/health |

Open http://localhost:3000 and you should see the quotation system home page. The AI assistant page at http://localhost:3000/agent only responds once you have built the agent.

---

## 4. Configure MCP for your AI coding tool (before you start developing)

Before feeding the spec to your AI coding tool, set up the MCP servers / skills below so the AI can read current documentation and drive a browser:

| Tool | Purpose | Setup |
|------|---------|-------|
| google-agents-cli skills | Official skills for the ADK workflow, scaffold, eval, deploy | `uvx google-agents-cli setup` |
| ADK Docs MCP Server | Official ADK documentation | https://google.github.io/adk-docs/tutorials/coding-with-ai/#adk-docs-mcp-server |
| Context7 MCP | Current docs for any library | https://context7.com/docs/resources/all-clients |
| Playwright-MCP | Lets the AI drive a browser for E2E | https://github.com/microsoft/playwright-mcp?tab=readme-ov-file#getting-started |
| chrome-devtools-mcp (optional) | Lets the AI inspect Console / Network | https://github.com/ChromeDevTools/chrome-devtools-mcp?tab=readme-ov-file#getting-started |

---

## 5. Develop and verify

### Step 7: Hand the requirements prompt to your AI coding tool

`agent-spec-prompt.md` is the complete requirement to feed to the AI. The backend, frontend Chat UI, MCP server and database are already provided; you only build the ADK agent in `agent/`. The AI implements it in five stages and stops after each one for you to verify.

> Until the agent exists, the chat at http://localhost:3000/agent shows an error. That is expected.

### Step 8: Tests

```bash
# Frontend E2E (local)
cd frontend && bun install && bun run e2e

# Frontend E2E (container)
docker compose run --rm e2e

# Agent unit tests and offline integration tests (no API key; integration tests need the MCP server reachable locally)
cd agent && uv sync --group dev && uv run pytest tests/unit tests/integration -q

# Agent evaluation (needs an API key, backend and MCP server running)
cd agent && agents-cli eval run

# Agent self-acceptance score (0–100; run at the repo root, same prerequisites, about 3 minutes)
python3 scripts/grading/grade_agent.py --suite scripts/grading/student-suite.json
```

The score runs the two datasets required by the spec plus two extra cases, and queries the backend to confirm the original quotation is untouched and the copies and order really exist. The report is written to `artifacts/grading/<timestamp>/report.md`. Teaching assistants grade with a different, private dataset but the same script.

### Step 9: Agent trustworthiness evaluation lab

Once the agent is done, evaluate it with `agents-cli eval`. There are two versions:

| Version | File | Time | Content |
|---|---|---|---|
| In class | [eval-lab-quick.md](eval-lab-quick.md) | 25 min | Run one dataset, read per-case reasons, add a case that exposes a blind spot in the grading rules, break test |
| Full (take home) | [eval-lab.md](eval-lab.md) | 60–90 min | Fix grading rules, run the data-changing action dataset, stability comparison, write your own multi-turn case, write a one-page trustworthiness report |

**Prerequisites**

- The agent from Step 7 is done, `docker compose ps` shows db, backend, mcp-server, agent and frontend running, and the test data is loaded (Step 5).
- `agent/.env` has credentials (AI Studio `GEMINI_API_KEY`, or Vertex AI `GOOGLE_GENAI_USE_VERTEXAI=true` + `GOOGLE_CLOUD_PROJECT`) and `MCP_URL=http://localhost:8010/mcp`.
- You have run `uv sync --group dev --extra eval` inside `agent/`.

**Cost**: the in-class version makes about 15 Gemini calls, the full version about 40 to 60. The AI Studio free tier covers both.
