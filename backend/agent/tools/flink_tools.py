"""
Flink SQL 相关 Tools（Phase 1）
覆盖：generate_flink_sql / validate_sql / submit_sql_job / get_job_status
"""
import os
import time
from pathlib import Path
import requests
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

GATEWAY_URL = os.getenv("FLINK_SQL_GATEWAY_URL", "http://flink-sql-gateway:8083")
FLINK_REST_URL = os.getenv("FLINK_REST_URL", "http://flink-jobmanager:8081")

# 加载系统提示词（SQL 生成专用，复用 prompts/ 目录下的文件）
_PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "system_prompt.md"
_SQL_SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8") if _PROMPT_FILE.exists() else "You are a Flink SQL expert."


def _get_llm() -> ChatOpenAI:
    """构建 LLM 实例（用于 generate_flink_sql Tool 内部调用）"""
    return ChatOpenAI(
        model=os.environ["LLM_MODEL"],
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
        temperature=0,
    )


# ─────────────────────────────────────────────────────────────
# Session 管理（轻量，不做持久化；Phase 3+ 可改为 DB 存储）
# ─────────────────────────────────────────────────────────────

def _ensure_valid_session(session_id: str | None) -> str:
    """
    检测 session_id 是否有效。
    - 无效或 None → 创建新 Session，返回新 handle
    - 有效          → 直接返回原 session_id
    """
    if session_id:
        resp = requests.get(f"{GATEWAY_URL}/v1/sessions/{session_id}", timeout=5)
        if resp.status_code == 200:
            return session_id

    new_resp = requests.post(f"{GATEWAY_URL}/v1/sessions", timeout=10)
    new_resp.raise_for_status()
    return new_resp.json()["sessionHandle"]


def _extract_readable_error(errors: list) -> str:
    """
    从 SQL Gateway 返回的 errors 列表中提取可读的错误信息。
    errors 通常是 ["Internal server error.", "<Exception on server side:\\n...Java 堆栈..."]
    我们解析 Java 堆栈，找到 "Caused by:" 最后一个根因中的实际错误消息。
    """
    for error_text in errors:
        if "Caused by:" in error_text:
            # 找到最后一个 Caused by 行，通常包含最具体的错误
            lines = error_text.split("\\n")
            caused_by_lines = [l.strip() for l in lines if "Caused by:" in l or "ValidationException" in l or "SqlGatewayException" in l]
            if caused_by_lines:
                # 优先取 ValidationException 信息
                for line in caused_by_lines:
                    if "ValidationException" in line or "SQL validation" in line:
                        # 提取冒号后的实际消息
                        msg = line.split(":", 1)[-1].strip() if ":" in line else line
                        return msg
                # 否则取最后一个 Caused by
                last = caused_by_lines[-1]
                return last.split(":", 1)[-1].strip() if ":" in last else last
        elif error_text and "Internal server error" not in error_text:
            return error_text
    return str(errors) if errors else "未知错误"


def _wait_for_result(session_id: str, operation_handle: str, timeout: int = 30) -> dict:
    """
    轮询 SQL Gateway 获取 statement 执行结果（RUNNING → FINISHED/ERROR）。
    ERROR 状态时从 result/0 的 HTTP 500 响应体中提取真实错误信息。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        status_resp = requests.get(
            f"{GATEWAY_URL}/v1/sessions/{session_id}/operations/{operation_handle}/status",
            timeout=5,
        )
        status_resp.raise_for_status()
        status = status_resp.json().get("status")

        if status in ("FINISHED", "ERROR", "CANCELED"):
            # 无论状态码都尝试读 result（ERROR 时是 HTTP 500 with JSON body）
            result_resp = requests.get(
                f"{GATEWAY_URL}/v1/sessions/{session_id}/operations/{operation_handle}/result/0",
                timeout=5,
            )
            result_data = {}
            error_msg = ""

            try:
                result_json = result_resp.json()
                if status == "ERROR":
                    # HTTP 500 响应体格式：{"errors": ["Internal server error.", "<Exception...Caused by: ...>"]}
                    errors = result_json.get("errors", [])
                    error_msg = _extract_readable_error(errors)
                else:
                    result_data = result_json
            except Exception:
                error_msg = result_resp.text[:500] if result_resp.text else "无法解析错误信息"

            return {
                "status": status,
                "result": result_data,
                "error_detail": error_msg,
                "operation_handle": operation_handle,
                "session_id": session_id,
            }

        time.sleep(1)

    return {
        "status": "TIMEOUT",
        "error_detail": f"等待超时（{timeout}s），operation_handle={operation_handle}",
        "operation_handle": operation_handle,
        "session_id": session_id,
    }


# ─────────────────────────────────────────────────────────────
# Tool 定义
# ─────────────────────────────────────────────────────────────

@tool
def generate_flink_sql(description: str, previous_error: str = "") -> dict:
    """
    根据用户的自然语言描述生成 Flink SQL（面向 Flink 2.2 语法）。

    参数：
    - description:     用户的需求描述（自然语言）
    - previous_error:  上一次 validate_sql 返回的错误信息（非空时表示需要修复）

    返回：
    - sql: str         — 生成的 Flink SQL 语句
    - explanation: str — 对 SQL 的简要说明
    """
    llm = _get_llm()

    user_content = f"需求描述：\n{description}"
    if previous_error:
        user_content += (
            f"\n\n上一次生成的 SQL 验证失败，错误信息如下，请修复：\n```\n{previous_error}\n```"
        )

    messages = [
        SystemMessage(content=_SQL_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]
    response = llm.invoke(messages)
    raw = response.content

    # 尝试从 markdown 代码块中提取 SQL
    sql = ""
    explanation = ""
    if "```sql" in raw:
        parts = raw.split("```sql", 1)
        explanation = parts[0].strip()
        sql_block = parts[1].split("```", 1)[0].strip()
        sql = sql_block
    elif "```" in raw:
        parts = raw.split("```", 1)
        explanation = parts[0].strip()
        sql_block = parts[1].split("```", 1)[0].strip()
        sql = sql_block
    else:
        # 没有代码块时，整段作为 SQL 返回
        sql = raw.strip()

    return {"sql": sql, "explanation": explanation, "raw": raw}



def _split_sql_statements(sql: str) -> list[str]:
    """按分号分割 SQL 语句，去掉空白和空语句。注意：简单分割不处理字符串中的分号。"""
    stmts = [s.strip() for s in sql.split(";")]
    return [s for s in stmts if s and not s.startswith("--")]


@tool
def validate_sql(sql: str, session_id: str | None = None) -> dict:
    """
    用 Flink SQL Gateway 的 EXPLAIN 语句验证 SQL 语法和语义是否正确。
    支持多条语句（用 ; 分隔）：会先执行所有 DDL 建表，再对 INSERT INTO 语句做 EXPLAIN 验证。

    返回：
    - valid: bool     — 是否通过验证
    - error: str      — 错误信息（valid=False 时有内容），用于送回 LLM 修复
    - session_id: str — 当前有效的 Session handle（可复用到后续调用）
    """
    session_id = _ensure_valid_session(session_id)
    stmts = _split_sql_statements(sql)

    if not stmts:
        return {"valid": False, "error": "未解析到有效 SQL 语句", "session_id": session_id}

    ddl_stmts = [s for s in stmts if not s.upper().lstrip().startswith("INSERT")]
    insert_stmts = [s for s in stmts if s.upper().lstrip().startswith("INSERT")]

    # Step 1: 执行所有 DDL（建表），必须先建表才能 EXPLAIN INSERT INTO
    for ddl in ddl_stmts:
        resp = requests.post(
            f"{GATEWAY_URL}/v1/sessions/{session_id}/statements",
            json={"statement": ddl},
            timeout=10,
        )
        resp.raise_for_status()
        op_handle = resp.json()["operationHandle"]
        result = _wait_for_result(session_id, op_handle, timeout=15)
        if result["status"] != "FINISHED":
            error_msg = result.get("error_detail", "建表失败")
            return {"valid": False, "error": f"DDL 执行失败: {error_msg}", "session_id": session_id}

    # Step 2: 对每个 INSERT INTO 语句做 EXPLAIN 验证
    for insert in insert_stmts:
        resp = requests.post(
            f"{GATEWAY_URL}/v1/sessions/{session_id}/statements",
            json={"statement": f"EXPLAIN {insert}"},
            timeout=10,
        )
        resp.raise_for_status()
        op_handle = resp.json()["operationHandle"]
        result = _wait_for_result(session_id, op_handle)
        if result["status"] != "FINISHED":
            error_msg = result.get("error_detail", "") or "未知验证错误"
            return {"valid": False, "error": error_msg, "session_id": session_id}

    # 无 INSERT INTO 语句时，仅验证 DDL 成功即可
    return {"valid": True, "error": "", "session_id": session_id}


@tool
def submit_sql_job(sql: str, session_id: str | None = None) -> dict:
    """
    提交 Flink SQL 作业到 SQL Gateway（Session Mode）。
    支持多条语句（用 ; 分隔）： DDL 建表语句会等待完成，INSERT INTO 语句提交后立即返回。
    内置 Session 失效检测：若 Session 已过期，自动创建新 Session 再提交。

    返回：
    - operation_handle: str — INSERT INTO 的操作 handle
    - session_id: str       — 当前有效的 Session handle
    - status: str           — SUBMITTED
    """
    session_id = _ensure_valid_session(session_id)
    stmts = _split_sql_statements(sql)

    if not stmts:
        return {"status": "ERROR", "error": "未解析到有效 SQL 语句", "session_id": session_id}

    ddl_stmts = [s for s in stmts if not s.upper().lstrip().startswith("INSERT")]
    insert_stmts = [s for s in stmts if s.upper().lstrip().startswith("INSERT")]

    # Step 1: 执行所有 DDL
    for ddl in ddl_stmts:
        resp = requests.post(
            f"{GATEWAY_URL}/v1/sessions/{session_id}/statements",
            json={"statement": ddl},
            timeout=10,
        )
        resp.raise_for_status()
        op_handle = resp.json()["operationHandle"]
        result = _wait_for_result(session_id, op_handle, timeout=20)
        if result["status"] != "FINISHED":
            return {
                "status": "ERROR",
                "error": f"DDL 执行失败: {result.get('error_detail', '公')}",
                "session_id": session_id,
            }

    # Step 2: 提交所有 INSERT INTO（流式作业，提交后不需要等待）
    last_op_handle = None
    for insert in insert_stmts:
        resp = requests.post(
            f"{GATEWAY_URL}/v1/sessions/{session_id}/statements",
            json={"statement": insert},
            timeout=10,
        )
        resp.raise_for_status()
        last_op_handle = resp.json()["operationHandle"]

    if not last_op_handle:
        # 没有 INSERT INTO，只有 DDL
        return {"status": "FINISHED", "message": "DDL 执行完成", "session_id": session_id}

    # 等待作业注册到 Flink JobManager（流式作业启动需要几秒）
    flink_job_id = None
    for _ in range(8):   # 最多等 8 秒
        time.sleep(1)
        try:
            overview = requests.get(f"{FLINK_REST_URL}/jobs/overview", timeout=5)
            if overview.ok:
                jobs = overview.json().get("jobs", [])
                # 取最近启动的 RUNNING 作业
                running = sorted(
                    [j for j in jobs if j["state"] == "RUNNING"],
                    key=lambda j: j.get("start-time", 0),
                    reverse=True,
                )
                if running:
                    flink_job_id = running[0]["jid"]
                    break
        except Exception:
            pass

    result = {
        "operation_handle": last_op_handle,
        "session_id": session_id,
        "status": "SUBMITTED",
    }
    if flink_job_id:
        result["job_id"] = flink_job_id
        result["message"] = (
            f"作业已成功提交并运行。\n"
            f"Flink job_id: `{flink_job_id}`\n"
            f"Flink Web UI: http://localhost:8081/#/job/{flink_job_id}/overview"
        )
    else:
        result["message"] = (
            f"SQL 已提交，operation_handle={last_op_handle}。"
            "作业可能还在启动中，请稍后在 http://localhost:8081 查看 job_id。"
        )
    return result


@tool
def get_job_status(job_id: str) -> dict:
    """
    查询 Flink 作业的当前状态，通过 Flink REST API 获取。

    参数：
    - job_id: Flink REST API 返回的 jobId（32 位 hex，有无连字符均可接受）

    返回：
    - status: str      — RUNNING / FINISHED / FAILED / CANCELED
    - start_time: int  — 作业启动时间（毫秒时间戳）
    - duration: int    — 已运行时长（毫秒）

    注意：submit_sql_job 返回的是 operation_handle（SQL Gateway 内部 ID），
    不是 Flink job_id。如果不知道 job_id，请引导用户在 http://localhost:8081 查看。
    """
    # Flink REST API job_id 是 32 位无连字符 hex，去掉可能的连字符
    clean_id = job_id.replace("-", "")

    try:
        resp = requests.get(f"{FLINK_REST_URL}/jobs/{clean_id}", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return {
            "job_id": clean_id,
            "status": data.get("state", "UNKNOWN"),
            "name": data.get("name", ""),
            "start_time": data.get("start-time", 0),
            "duration": data.get("duration", 0),
        }
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return {
                "job_id": clean_id,
                "status": "NOT_FOUND",
                "error": f"作业 {clean_id} 不存在。可能原因：① operation_handle 不是 Flink job_id；② 作业尚未注册到 REST API。请在 http://localhost:8081 查看真实 job_id。",
            }
        raise


@tool
def get_job_exceptions(job_id: str) -> dict:
    """
    获取 Flink 作业的异常日志，用于 Agent 诊断作业失败原因。

    返回：
    - root_exception: str    — 根因异常信息
    - all_exceptions: list   — 所有异常列表
    """
    resp = requests.get(f"{FLINK_REST_URL}/jobs/{job_id}/exceptions", timeout=5)
    resp.raise_for_status()
    data = resp.json()

    return {
        "job_id": job_id,
        "root_exception": data.get("root-exception", ""),
        "all_exceptions": data.get("all-exceptions", []),
    }


@tool
def kill_job(job_id: str) -> dict:
    """
    停止 Flink 作业。
    ⚠️ 高风险操作：此 Tool 在图中配置了 human-in-the-loop，LangGraph 会在执行前暂停等待用户确认。

    参数：
    - job_id: Flink 作业 ID（32 位 hex）
    """
    resp = requests.patch(
        f"{FLINK_REST_URL}/jobs/{job_id}",
        params={"mode": "cancel"},
        timeout=10,
    )
    resp.raise_for_status()
    return {"job_id": job_id, "status": "CANCELING", "message": "停止指令已发送"}


# 导出给 graph.py 使用
# 注意：generate_flink_sql 已从 PHASE1_TOOLS 中移除。
# 外层 Agent LLM 直接在推理中生成 SQL 并传给 validate_sql，避免双重 LLM 调用。
PHASE1_TOOLS = [
    validate_sql,
    submit_sql_job,
    get_job_status,
    get_job_exceptions,
    kill_job,
]
HIGH_RISK_TOOLS = ["kill_job"]  # 这里列出的 Tool 必须在图中配置 human-in-the-loop
