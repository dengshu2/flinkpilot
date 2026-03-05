# Agent 设计：LangGraph 图与 Tool 体系

> 迁移自 flinkpilot_architecture.md § 三、技术栈选型
> 上次更新：2026-03-05（已实现 Phase 1 完整图结构）

---

## LangGraph 图结构（Phase 1 实现版）

Flink 场景是典型的多步骤 ReAct 循环：

```
用户输入
  ↓
agent（LLM 推理）
  ↓ 有 tool_calls
tools（ToolNode ♻）
  ↓
route_after_tools
  ├─ validate_sql 失败 & retry_count < 3  →  handle_validate_failure → agent（重试）
  ├─ validate_sql 失败 & retry_count ≥ 3  →  END（报告失败）
  ├─ 高风险操作（kill_job）                  →  human_review → agent
  └─ 其他                                      →  agent
```

**关键实现细节：**

| 组件 | 说明 |
|------|------|
| `AgentState.last_sql_error` | 存储上次 validate_sql 的错误信息，在 agent_node 中注入 System Prompt |
| `AgentState.sql_retry_count` | 重试计数，达到 `MAX_SQL_RETRIES=3` 时路由到 END |
| `handle_validate_failure` 节点 | 递增 retry_count，提取 error 写入 State |
| `route_after_tools` | 解析 ToolMessage.content JSON，判断 validate_sql 的 `valid` 字段 |

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

### Phase 1 Tools（SQL 路径）（已全部实现）

```python
@tool
def generate_flink_sql(description: str, previous_error: str = "") -> dict:
    """根据用户描述生成 Flink SQL（Flink 2.x 语法）。
    previous_error 非空时，将错误信息带入 LLM 请求以生成修复后的 SQL。
    返回 {sql, explanation, raw}"""
    ...

@tool
def validate_sql(sql: str, session_id: str | None = None) -> dict:
    """用 Flink EXPLAIN 验证 SQL 语法，返回 {valid, error, session_id}"""
    ...

@tool
def submit_sql_job(sql: str, session_id: str | None = None) -> dict:
    """提交 SQL 作业，内置 Session 失效检测与自动重建"""
    ...

@tool
def get_job_status(job_id: str) -> dict:
    """轮询 Flink REST API 获取作业状态"""
    ...

@tool
def get_job_exceptions(job_id: str) -> dict:
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
