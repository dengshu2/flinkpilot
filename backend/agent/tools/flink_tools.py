"""
Flink SQL 相关 Tools（Phase 1）
覆盖：generate_flink_sql / validate_sql / submit_sql_job / get_job_status
"""
import os
import time
import requests
from langchain_core.tools import tool

GATEWAY_URL = os.getenv("FLINK_SQL_GATEWAY_URL", "http://flink-sql-gateway:8083")
FLINK_REST_URL = os.getenv("FLINK_REST_URL", "http://flink-jobmanager:8081")


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


def _wait_for_result(session_id: str, operation_handle: str, timeout: int = 30) -> dict:
    """
    轮询 SQL Gateway 获取 statement 执行结果（RUNNING → FINISHED/ERROR）。
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
            result_resp = requests.get(
                f"{GATEWAY_URL}/v1/sessions/{session_id}/operations/{operation_handle}/result/0",
                timeout=5,
            )
            return {
                "status": status,
                "result": result_resp.json() if result_resp.ok else {},
                "operation_handle": operation_handle,
                "session_id": session_id,
            }

        time.sleep(1)

    return {
        "status": "TIMEOUT",
        "operation_handle": operation_handle,
        "session_id": session_id,
    }


# ─────────────────────────────────────────────────────────────
# Tool 定义
# ─────────────────────────────────────────────────────────────

@tool
def validate_sql(sql: str, session_id: str | None = None) -> dict:
    """
    用 Flink SQL Gateway 的 EXPLAIN 语句验证 SQL 语法和语义是否正确。

    返回：
    - valid: bool     — 是否通过验证
    - error: str      — 错误信息（valid=False 时有内容），用于送回 LLM 修复
    - session_id: str — 当前有效的 Session handle（可复用到后续调用）
    """
    session_id = _ensure_valid_session(session_id)

    resp = requests.post(
        f"{GATEWAY_URL}/v1/sessions/{session_id}/statements",
        json={"statement": f"EXPLAIN {sql}"},
        timeout=10,
    )
    resp.raise_for_status()
    op_handle = resp.json()["operationHandle"]

    result = _wait_for_result(session_id, op_handle)

    if result["status"] == "FINISHED":
        return {"valid": True, "error": "", "session_id": session_id, "detail": result}
    else:
        # 从结果中提取错误信息
        error_msg = str(result.get("result", {}).get("errors", result.get("result", "")))
        return {"valid": False, "error": error_msg, "session_id": session_id, "detail": result}


@tool
def submit_sql_job(sql: str, session_id: str | None = None) -> dict:
    """
    提交 Flink SQL 作业到 SQL Gateway（Session Mode）。
    内置 Session 失效检测：若 Session 已过期，自动创建新 Session 再提交。

    返回：
    - operation_handle: str — 本次提交的操作 handle
    - session_id: str       — 当前有效的 Session handle
    - status: str           — RUNNING / FINISHED / ERROR
    """
    session_id = _ensure_valid_session(session_id)

    resp = requests.post(
        f"{GATEWAY_URL}/v1/sessions/{session_id}/statements",
        json={"statement": sql},
        timeout=10,
    )
    resp.raise_for_status()
    op_handle = resp.json()["operationHandle"]

    return {
        "operation_handle": op_handle,
        "session_id": session_id,
        "status": "SUBMITTED",
        "message": f"SQL 已提交，operation_handle={op_handle}，使用 get_job_status 查询作业状态",
    }


@tool
def get_job_status(job_id: str) -> dict:
    """
    查询 Flink 作业的当前状态，通过 Flink REST API 获取。

    参数：
    - job_id: Flink REST API 返回的 jobId（格式：32 位 hex）

    返回：
    - status: str      — RUNNING / FINISHED / FAILED / CANCELED
    - start_time: int  — 作业启动时间（毫秒时间戳）
    - duration: int    — 已运行时长（毫秒）
    """
    resp = requests.get(f"{FLINK_REST_URL}/jobs/{job_id}", timeout=5)
    resp.raise_for_status()
    data = resp.json()

    return {
        "job_id": job_id,
        "status": data.get("state", "UNKNOWN"),
        "name": data.get("name", ""),
        "start_time": data.get("start-time", 0),
        "duration": data.get("duration", 0),
    }


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
PHASE1_TOOLS = [validate_sql, submit_sql_job, get_job_status, get_job_exceptions, kill_job]
HIGH_RISK_TOOLS = ["kill_job"]  # 这里列出的 Tool 必须在图中配置 human-in-the-loop
