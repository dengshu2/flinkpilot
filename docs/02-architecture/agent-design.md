# Agent 设计：LangGraph 图与 Tool 体系

> 迁移自 flinkpilot_architecture.md § 三、技术栈选型
> 上次更新：2026-03-05

---

## LangGraph 图结构

Flink 场景是典型的多步骤 ReAct 循环：

```
用户输入
  ↓
理解意图（LLM）
  ↓
生成 Flink SQL
  ↓
validate_sql（EXPLAIN）── 失败 ──→ 报错送回 LLM 重试（最多 3 次）
  ↓ 成功
submit_sql_job（含 Session 失效检测）
  ↓
get_job_status 轮询
  ↓
get_job_metrics / get_job_exceptions（异常时）
  ↓
诊断建议 → 用户
```

**LangGraph 1.0 关键特性在本项目的应用：**

| 特性 | 应用场景 |
|------|---------|
| **Durable State** | 状态自动持久化到 PostgreSQL，VPS 重启后长流程（生成→打包→部署）从断点续跑 |
| **Built-in Persistence** | 会话历史天然存储 |
| **Human-in-the-loop** | `kill_job` 等高风险操作执行前暂停等待用户确认 |

---

## 后端入口：FastAPI + WebSocket

```python
from fastapi import FastAPI, WebSocket
from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres import PostgresSaver

app = FastAPI()

# PostgreSQL 做持久化 checkpointer（和业务 DB 同一个实例）
checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)
agent = build_agent(checkpointer=checkpointer)

@app.websocket("/ws/chat/{session_id}")
async def chat_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    while True:
        user_msg = await websocket.receive_text()
        # 流式返回 Agent 推理过程
        async for chunk in agent.astream(
            {"messages": [user_msg]},
            config={"configurable": {"thread_id": session_id}}
        ):
            await websocket.send_text(chunk)
```

---

## Tool 体系（核心 Skills）

### Phase 1 Tools（SQL 路径）

```python
from langchain_core.tools import tool
import requests

@tool
def generate_flink_sql(description: str) -> str:
    """根据用户描述生成 Flink SQL（Flink 2.x 语法）"""
    ...

@tool
def validate_sql(sql: str, session_id: str) -> dict:
    """用 Flink EXPLAIN 验证 SQL 语法，返回错误信息供修复循环使用"""
    resp = requests.post(
        f"{GATEWAY_URL}/v1/sessions/{session_id}/statements",
        json={"statement": f"EXPLAIN {sql}"}
    )
    return resp.json()

@tool
def submit_sql_job(sql: str, session_id: str) -> dict:
    """提交 SQL 作业，内置 Session 失效检测与自动重建"""
    # Session 有效性检测
    check = requests.get(f"{GATEWAY_URL}/v1/sessions/{session_id}")
    if check.status_code != 200:
        new_session = requests.post(f"{GATEWAY_URL}/v1/sessions").json()
        session_id = new_session["sessionHandle"]
    resp = requests.post(
        f"{GATEWAY_URL}/v1/sessions/{session_id}/statements",
        json={"statement": sql}
    )
    return {**resp.json(), "session_id": session_id}

@tool
def get_job_metrics(job_id: str) -> dict:
    """获取作业指标：TPS、延迟、Backpressure"""
    resp = requests.get(f"{FLINK_REST_URL}/jobs/{job_id}/metrics")
    return resp.json()

@tool
def get_job_exceptions(job_id: str) -> str:
    """获取作业异常日志，用于 Agent 诊断"""
    ...

@tool
def kill_job(job_id: str) -> dict:
    """停止作业（执行前触发 human-in-the-loop 确认）"""
    ...
```

### Phase 2 Tools（JAR 路径）

```python
@tool
def generate_java_code(description: str) -> str:
    """生成 DataStream Java 代码（必须指定 Flink DataStream API V2 风格）"""
    ...

@tool
def build_jar(java_code: str) -> dict:
    """在独立 Maven 构建容器内打包 JAR，隔离依赖"""
    ...

@tool
def deploy_jar(jar_path: str) -> dict:
    """上传 JAR 到 Flink REST API 并提交作业"""
    ...
```

---

## 操作风险等级

| 操作 | 风险等级 | 是否需要 Human-in-the-loop |
|------|---------|--------------------------|
| generate_flink_sql | 🟢 低 | 否 |
| validate_sql | 🟢 低 | 否 |
| submit_sql_job | 🟡 中 | 建议确认（首次提交） |
| get_job_metrics | 🟢 低 | 否 |
| get_job_exceptions | 🟢 低 | 否 |
| kill_job | 🔴 高 | **是，必须等待用户确认** |
| DROP TABLE / 修改 Checkpoint 策略 | 🔴 高 | **是，必须等待用户确认** |

---

## 文件目录约定

```
backend/
├── main.py               # FastAPI 入口，WebSocket 端点
└── agent/
    ├── graph.py          # LangGraph 状态图定义（含 PostgresSaver）
    ├── tools/
    │   ├── flink_tools.py    # SQL 相关 Tool
    │   ├── build_tools.py    # JAR 构建相关 Tool（Phase 2）
    │   └── monitor_tools.py  # 监控诊断 Tool
    └── prompts/
        └── system_prompt.md  # Agent 系统提示词
```
