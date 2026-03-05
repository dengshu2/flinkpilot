# 后端开发指南

> 上次更新：2026-03-05
> 适用阶段：Phase 1-2

---

## 环境要求

- Python 3.11+
- Docker & Docker Compose

## 依赖安装

```bash
cd backend
pip install -r requirements.txt
```

### requirements.txt

```
langgraph>=1.0.0
langchain-openai>=0.3.0
fastapi
uvicorn
psycopg[binary]>=3.1.0   # psycopg3，不是 psycopg2-binary
requests
```

> ⚠️ 必须使用 `psycopg[binary]>=3.1.0`（psycopg3）。LangGraph 1.0 的 `PostgresSaver` 依赖 psycopg3，使用 `psycopg2-binary` 会导致运行时错误。

---

## 启动后端

```bash
# 确保 Docker Compose 服务已启动（PostgreSQL 等依赖）
docker compose up -d db

# 开发模式启动（热重载）
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 新增 Tool 的步骤

1. 在 `backend/agent/tools/` 下找到合适的文件（`flink_tools.py` / `build_tools.py` / `monitor_tools.py`）
2. 使用 `@tool` 装饰器定义新 Tool，docstring 是 LLM 选择该 Tool 的依据，**必须写清楚**
3. 在 `backend/agent/graph.py` 中将新 Tool 注册到 LangGraph 图的工具列表
4. 确认操作风险等级，高风险操作必须加 human-in-the-loop（见 [agent-design.md](../02-architecture/agent-design.md)）
5. 在 `docs/06-roadmap/progress.md` 中勾选对应任务

---

## LangGraph 图修改注意事项

- 修改图结构后，旧的 PostgreSQL checkpoint 可能与新版图不兼容，本地测试时可以清空 DB 重来
- `PostgresSaver.from_conn_string()` 使用 `DATABASE_URL` 环境变量
- `thread_id` 对应前端的 WebSocket `session_id`，同一 thread_id 的请求共享状态

---

## 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `LLM_API_KEY` | LLM 服务 API Key | sk-xxx |
| `LLM_BASE_URL` | LLM API 地址 | https://api.openai.com/v1 |
| `FLINK_REST_URL` | Flink REST API | http://flink-jobmanager:8081 |
| `FLINK_SQL_GATEWAY_URL` | SQL Gateway | http://flink-sql-gateway:8083 |
| `DATABASE_URL` | PostgreSQL 连接串 | postgresql://postgres:secret@db:5432/flinkpilot |
