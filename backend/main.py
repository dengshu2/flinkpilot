"""
FlinkPilot FastAPI 入口
- WebSocket /ws/chat/{session_id}：流式 Agent 对话
- POST /api/chat：简单 HTTP 模式（调试用）
- GET /health：健康检查
"""
import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import HumanMessage

load_dotenv()

from agent.graph import build_agent

# ─────────────────────────────────────────────────────────────
# 应用初始化
# ─────────────────────────────────────────────────────────────
_checkpointer: PostgresSaver | None = None
_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用启动时：
    1. 初始化 PostgresSaver（psycopg3 连接）
    2. 运行 checkpointer.setup()（自动建表，幂等）
    3. 编译 LangGraph 图
    """
    global _checkpointer, _agent

    db_url = os.environ["DATABASE_URL"]
    _checkpointer = PostgresSaver.from_conn_string(db_url)
    _checkpointer.setup()  # 创建 langgraph_checkpoints 等内部表（幂等）

    _agent = build_agent(checkpointer=_checkpointer)
    print("FlinkPilot Agent 初始化完成")

    yield

    # 清理（PostgresSaver 无需显式关闭）


app = FastAPI(
    title="FlinkPilot API",
    description="自然语言驱动 Apache Flink 数据流的 AI Agent 平台",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Phase 3 生产时收紧
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────
# 路由
# ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "agent_ready": _agent is not None}


@app.websocket("/ws/chat/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str):
    """
    WebSocket 流式对话端点。

    客户端发送：{"message": "用户输入内容"}
    服务端流式返回：
    - {"type": "thinking", "content": "..."}   — Agent 推理过程
    - {"type": "tool_call", "tool": "..."}      — 正在调用的 Tool
    - {"type": "message", "content": "..."}     — 最终回复
    - {"type": "interrupt", "reason": "..."}    — human-in-the-loop 确认请求
    - {"type": "error", "detail": "..."}        — 错误
    """
    await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            user_input = data.get("message", "").strip()
            resume_value = data.get("resume")  # human-in-the-loop 确认值

            if not user_input and resume_value is None:
                continue

            config = {"configurable": {"thread_id": session_id}}

            # human-in-the-loop 恢复
            if resume_value is not None:
                async for chunk in _agent.astream(
                    None,  # None 表示从 interrupt 点恢复
                    config=config,
                    stream_mode="messages",
                ):
                    await _stream_chunk(websocket, chunk)
                continue

            # 普通用户消息
            async for chunk in _agent.astream(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
                stream_mode="messages",
            ):
                await _stream_chunk(websocket, chunk)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_text(json.dumps({"type": "error", "detail": str(e)}))


async def _stream_chunk(websocket: WebSocket, chunk):
    """将 LangGraph astream chunk 序列化并推送给客户端"""
    # chunk 是 (messages, metadata) 元组
    if isinstance(chunk, tuple):
        msg, meta = chunk
        node = meta.get("langgraph_node", "")

        if hasattr(msg, "content") and msg.content:
            await websocket.send_text(
                json.dumps({"type": "message", "content": msg.content, "node": node})
            )
        elif hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                await websocket.send_text(
                    json.dumps({"type": "tool_call", "tool": tc["name"], "args": tc["args"]})
                )
    # interrupt 事件
    elif isinstance(chunk, dict) and "__interrupt__" in chunk:
        interrupt_info = chunk["__interrupt__"]
        await websocket.send_text(
            json.dumps({"type": "interrupt", "reason": str(interrupt_info)})
        )


@app.post("/api/chat")
async def http_chat(body: dict):
    """
    HTTP 简单模式（调试 / Gradio 使用）。
    非流式，等待完整结果后返回。
    """
    session_id = body.get("session_id", "debug")
    message = body.get("message", "")
    config = {"configurable": {"thread_id": session_id}}

    result = await _agent.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
    )

    last_msg = result["messages"][-1]
    return {
        "session_id": session_id,
        "reply": last_msg.content if hasattr(last_msg, "content") else str(last_msg),
    }
