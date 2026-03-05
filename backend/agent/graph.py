"""
FlinkPilot LangGraph 图定义（Phase 1）

流程：
  用户输入
    → agent（LLM 推理，选择 Tool）
    → tools（Tool 执行）
    → route_after_tools：
        - validate_sql 失败 且 retry_count < 3  → 回 agent 重试
        - validate_sql 失败 且 retry_count >= 3 → END（报告失败）
        - 高风险操作完成                         → human_review
        - 其他                                   → agent
    → [human_review 等待确认，仅高风险操作]
    → agent 继续
    → END

持久化：PostgresSaver（LangGraph 1.0 Durable State API）
"""
import os
import json
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agent.tools.flink_tools import PHASE1_TOOLS, HIGH_RISK_TOOLS

# ─────────────────────────────────────────────────────────────
# 系统提示词（从本地文件加载）
# ─────────────────────────────────────────────────────────────
_PROMPT_FILE = Path(__file__).parent / "prompts" / "system_prompt.md"
SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8")

MAX_SQL_RETRIES = 3


# ─────────────────────────────────────────────────────────────
# State 定义
# ─────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # 当前 SQL Gateway session handle，跨节点共享以复用 Session
    session_id: str | None
    # SQL 生成-验证重试计数（最多 MAX_SQL_RETRIES 次）
    sql_retry_count: int
    # 最近一次 validate_sql 失败的错误信息（注入给 LLM 用于修复）
    last_sql_error: str


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

    若 last_sql_error 非空，将错误信息注入 System Prompt，
    引导 LLM 生成修复后的 SQL。
    """
    system_content = SYSTEM_PROMPT

    # 将上一次 validate_sql 的错误注入 System Prompt，引导 LLM 修复
    if state.get("last_sql_error"):
        retry_count = state.get("sql_retry_count", 0)
        system_content += (
            f"\n\n---\n"
            f"## ⚠️ SQL 验证失败（第 {retry_count} 次尝试）\n\n"
            f"上一次生成的 SQL 在 EXPLAIN 验证时返回了以下错误：\n\n"
            f"```\n{state['last_sql_error']}\n```\n\n"
            f"请仔细分析错误原因，修正 SQL 后，重新调用 `validate_sql` 进行验证。\n"
            f"剩余重试次数：{MAX_SQL_RETRIES - retry_count}。"
        )

    messages = [SystemMessage(content=system_content)] + state["messages"]
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

    1. 若最后一条 ToolMessage 是 validate_sql 的失败结果：
       - retry_count < MAX_SQL_RETRIES → 更新 State 后回 agent 重试
       - retry_count >= MAX_SQL_RETRIES → END（超出重试次数，报告给用户）
    2. 若最后一条 ToolMessage 来自高风险操作 → human_review
    3. 其他情况 → 回 agent 继续推理
    """
    last_msg = state["messages"][-1]

    # 仅处理 ToolMessage
    if not isinstance(last_msg, ToolMessage):
        return "agent"

    tool_name = getattr(last_msg, "name", "")

    # ── validate_sql 失败处理 ──
    if tool_name == "validate_sql":
        try:
            result = json.loads(last_msg.content) if isinstance(last_msg.content, str) else last_msg.content
        except (json.JSONDecodeError, TypeError):
            result = {}

        if isinstance(result, dict) and not result.get("valid", True):
            retry_count = state.get("sql_retry_count", 0) + 1
            if retry_count >= MAX_SQL_RETRIES:
                # 超出重试次数，结束对话（Agent 在最后一条消息中已解释了失败原因）
                return END
            # 更新重试计数和错误信息（通过 State 更新传回图）
            # 注意：LangGraph 的路由函数不能直接修改 State，
            # 所以我们通过 validate_sql_retry 节点来修改
            return "handle_validate_failure"

    # ── 高风险操作 ──
    if tool_name in HIGH_RISK_TOOLS:
        return "human_review"

    return "agent"


def handle_validate_failure_node(state: AgentState):
    """
    处理 validate_sql 失败的中间节点：
    - 递增 sql_retry_count
    - 提取错误信息到 last_sql_error
    这两个 State 字段会在下一次 agent_node 执行时注入 System Prompt。
    """
    last_msg = state["messages"][-1]
    try:
        result = json.loads(last_msg.content) if isinstance(last_msg.content, str) else last_msg.content
    except (json.JSONDecodeError, TypeError):
        result = {}

    error_msg = ""
    if isinstance(result, dict):
        error_msg = result.get("error", str(result))

    return {
        "sql_retry_count": state.get("sql_retry_count", 0) + 1,
        "last_sql_error": error_msg,
    }


def reset_sql_state_node(state: AgentState):
    """
    validate_sql 成功后，清空重试计数和错误信息。
    在 submit_sql_job 之前执行，避免后续流程携带脏数据。
    """
    return {"sql_retry_count": 0, "last_sql_error": ""}


# ─────────────────────────────────────────────────────────────
# validate_sql 成功后的路由（决定是否重置重试状态再回 agent）
# ─────────────────────────────────────────────────────────────
def route_after_validate_success(state: AgentState) -> str:
    """在 handle_validate_failure 之后，回到 agent 重试"""
    return "agent"


# ─────────────────────────────────────────────────────────────
# 图构建
# ─────────────────────────────────────────────────────────────
def build_agent(checkpointer: AsyncPostgresSaver):
    """
    构建并编译 LangGraph ReAct 图（含 SQL 验证-修复重试循环）。

    参数：
    - checkpointer: PostgresSaver 实例（由 main.py 初始化后传入）

    返回：
    - 编译后的 CompiledGraph，支持 .invoke() / .astream()

    图结构：
        agent
          ↓ (有 tool_calls)
        tools
          ↓
        route_after_tools
          ├─ validate_sql 失败 & retry < 3 → handle_validate_failure → agent（重试）
          ├─ validate_sql 失败 & retry >= 3 → END
          ├─ 高风险操作                     → human_review → agent
          └─ 其他                           → agent
    """
    llm = _build_llm()
    llm_with_tools = llm.bind_tools(PHASE1_TOOLS)

    graph = StateGraph(AgentState)

    # 节点注册
    graph.add_node("agent", lambda state: agent_node(state, llm_with_tools))
    graph.add_node("tools", ToolNode(PHASE1_TOOLS))
    graph.add_node("human_review", human_review_node)
    graph.add_node("handle_validate_failure", handle_validate_failure_node)

    # 入口
    graph.set_entry_point("agent")

    # 边：agent → tools（若有 tool_calls） 或 END
    graph.add_conditional_edges("agent", tools_condition)

    # 边：tools 完成后路由
    graph.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "agent": "agent",
            "human_review": "human_review",
            "handle_validate_failure": "handle_validate_failure",
            END: END,
        },
    )

    # handle_validate_failure 后回到 agent 重试
    graph.add_edge("handle_validate_failure", "agent")

    # human_review 确认后回到 agent 继续
    graph.add_edge("human_review", "agent")

    return graph.compile(
        checkpointer=checkpointer,
        # kill_job 执行前暂停，等待用户通过 Command(resume=True) 确认
        interrupt_before=["human_review"],
    )
