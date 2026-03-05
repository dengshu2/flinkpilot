"""
FlinkPilot LangGraph 图定义（Phase 1）

流程：
  用户输入
    → generate_sql（LLM 节点）
    → validate_sql（EXPLAIN 验证，最多 3 次重试）
    → [human-in-the-loop 确认，仅高风险操作]
    → submit_sql_job / get_job_status / get_job_exceptions / kill_job
    → 结果返回用户

持久化：PostgresSaver（LangGraph 1.0 Durable State API）
"""
import os
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.postgres import PostgresSaver

from agent.tools.flink_tools import PHASE1_TOOLS, HIGH_RISK_TOOLS

# ─────────────────────────────────────────────────────────────
# 系统提示词（从本地文件加载）
# ─────────────────────────────────────────────────────────────
_PROMPT_FILE = Path(__file__).parent / "prompts" / "system_prompt.md"
SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────
# State 定义
# ─────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # 当前 SQL Gateway session handle，跨节点共享以复用 Session
    session_id: str | None
    # SQL 生成-验证重试计数（最多 3 次）
    sql_retry_count: int


# ─────────────────────────────────────────────────────────────
# LLM 模型初始化
# ─────────────────────────────────────────────────────────────
def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ["LLM_MODEL"],
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
        temperature=0,  # SQL 生成要确定性，不要创意
        streaming=True,
    )


# ─────────────────────────────────────────────────────────────
# 节点函数
# ─────────────────────────────────────────────────────────────
def agent_node(state: AgentState, llm_with_tools):
    """
    核心 LLM 推理节点：理解意图 → 选择 Tool → 生成参数
    """
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def human_review_node(state: AgentState):
    """
    Human-in-the-loop 节点。
    LangGraph 1.0：图运行到此节点时自动 interrupt，等待外部 Command(resume=...) 恢复。
    前端通过 /ws/chat/{session_id} 接收 interrupt 事件，展示确认对话框。
    此函数无需实际代码，节点本身由 interrupt_before 机制触发暂停。
    """
    pass  # 真正的拦截由 graph.compile(interrupt_before=["human_review"]) 实现


# ─────────────────────────────────────────────────────────────
# 路由函数
# ─────────────────────────────────────────────────────────────
def route_after_tools(state: AgentState) -> str:
    """
    Tool 执行完后判断下一步：
    - 若最后一个 Tool 调用是高风险操作 → 先路由到 human_review
    - 否则回到 agent 继续推理
    """
    last_msg = state["messages"][-1]

    # ToolMessage 时检测是否是高风险操作的返回
    if hasattr(last_msg, "name") and last_msg.name in HIGH_RISK_TOOLS:
        return "human_review"

    return "agent"


# ─────────────────────────────────────────────────────────────
# 图构建
# ─────────────────────────────────────────────────────────────
def build_agent(checkpointer: PostgresSaver):
    """
    构建并编译 LangGraph ReAct 图。

    参数：
    - checkpointer: PostgresSaver 实例（由 main.py 初始化后传入）

    返回：
    - 编译后的 CompiledGraph，支持 .invoke() / .astream()
    """
    llm = _build_llm()
    llm_with_tools = llm.bind_tools(PHASE1_TOOLS)

    graph = StateGraph(AgentState)

    # 节点注册
    graph.add_node("agent", lambda state: agent_node(state, llm_with_tools))
    graph.add_node("tools", ToolNode(PHASE1_TOOLS))
    graph.add_node("human_review", human_review_node)

    # 入口
    graph.set_entry_point("agent")

    # 边：agent → tools（若有 tool_calls） 或 END
    graph.add_conditional_edges("agent", tools_condition)

    # 边：tools 完成后路由
    graph.add_conditional_edges(
        "tools",
        route_after_tools,
        {"agent": "agent", "human_review": "human_review"},
    )

    # human_review 确认后回到 agent 继续
    graph.add_edge("human_review", "agent")

    return graph.compile(
        checkpointer=checkpointer,
        # kill_job 执行前暂停，等待用户通过 Command(resume=True) 确认
        interrupt_before=["human_review"],
    )
