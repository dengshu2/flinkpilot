"""
FlinkPilot Gradio MVP 前端（Phase 1）

功能：
- 对话框：调用 FastAPI /api/chat 接口（HTTP 非流式）
- 作业状态面板：调用 FastAPI /api/jobs/{job_id} 查询实时状态
- 简洁单页布局，专注验证 Agent 核心链路

启动：
    cd backend
    python gradio_app.py
    # 访问 http://localhost:7860
"""
import os
import uuid
import httpx
import gradio as gr

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


# ─────────────────────────────────────────────────────────────
# 后端通信函数
# ─────────────────────────────────────────────────────────────

def send_message(message: str, session_id: str, history: list) -> tuple[list, str, str]:
    """
    向 FastAPI /api/chat 发送用户消息，返回 Agent 回复。
    使用 HTTP 非流式接口（调试友好，Gradio 简单集成）。

    Gradio 6.x 的 Chatbot 需要字典格式：
    [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

    返回：(更新后的 history, 清空的输入框, session_id)
    """
    if not message.strip():
        return history, "", session_id

    # 先把用户消息写入，assistant 部分占位等待回复
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": ""},
    ]

    try:
        with httpx.Client(timeout=300.0) as client:
            resp = client.post(
                f"{BACKEND_URL}/api/chat",
                json={"message": message, "session_id": session_id},
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("reply", "（Agent 无回复）")
    except httpx.ConnectError:
        reply = "连接失败：请确认后端服务已启动（`uv run uvicorn main:app --port 8000`）。"
    except httpx.TimeoutException:
        reply = "请求超时（5 分钟）：Agent 链路耗时过长，请稍后重试，或简化你的需求描述。"
    except Exception as e:
        reply = f"请求出错：{str(e)}"

    history[-1]["content"] = reply
    return history, "", session_id


def query_job_status(job_id: str) -> str:
    """
    查询 Flink 作业状态，调用后端 /api/jobs/{job_id}。
    """
    job_id = job_id.strip()
    if not job_id:
        return "请输入作业 ID（32 位 hex 字符串）。"

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{BACKEND_URL}/api/jobs/{job_id}")
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "UNKNOWN")
        name = data.get("name", "—")
        duration_ms = data.get("duration", 0)
        duration_s = duration_ms // 1000

        status_emoji = {
            "RUNNING": "🟢 运行中",
            "FINISHED": "✅ 已完成",
            "FAILED": "🔴 失败",
            "CANCELED": "⚫ 已取消",
            "CANCELING": "⏹ 停止中",
        }.get(status, f"❓ {status}")

        return (
            f"**作业 ID**：`{job_id}`\n\n"
            f"**名称**：{name}\n\n"
            f"**状态**：{status_emoji}\n\n"
            f"**运行时长**：{duration_s} 秒"
        )
    except httpx.ConnectError:
        return "连接失败：请确认后端服务已启动。"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"作业不存在：`{job_id}`\n\n请确认作业 ID 是否正确。"
        return f"查询失败（HTTP {e.response.status_code}）：{e.response.text}"
    except Exception as e:
        return f"查询出错：{str(e)}"


def check_backend_health() -> str:
    """检查后端健康状态"""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{BACKEND_URL}/health")
            data = resp.json()
            if data.get("agent_ready"):
                return "🟢 后端正常，Agent 已就绪"
            else:
                return "🟡 后端运行中，Agent 尚未初始化"
    except Exception:
        return "🔴 无法连接后端，请检查服务是否启动"


# ─────────────────────────────────────────────────────────────
# Gradio UI 布局
# ─────────────────────────────────────────────────────────────

with gr.Blocks(
    title="FlinkPilot MVP",
) as demo:

    # ── Header ──
    gr.Markdown(
        """
        # FlinkPilot
        **自然语言驱动 Apache Flink 数据流的 AI Agent**

        描述你想要的流处理任务，Agent 会自动生成 SQL、验证并提交到 Flink。
        """
    )

    # ── 后端状态 ──
    with gr.Row():
        health_output = gr.Markdown(value="正在检查后端状态...", elem_classes=["status-box"])
        health_btn = gr.Button("刷新状态", size="sm", variant="secondary")

    gr.Markdown("---")

    # ── 主内容：左侧对话，右侧作业状态 ──
    with gr.Row(equal_height=True):

        # 左侧：对话区
        with gr.Column(scale=3):
            gr.Markdown("### 对话")

            chatbot = gr.Chatbot(
                label="Agent 对话",
                height=480,
                show_label=False,
                avatar_images=(None, "https://flink.apache.org/img/logo/png/100/flink_squirrel_100_color.png"),
            )

            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="例如：用 datagen 生成随机订单数据，每 10 秒统计一次各城市的 GMV，结果写入 PostgreSQL",
                    label="",
                    show_label=False,
                    lines=2,
                    max_lines=4,
                    scale=5,
                )
                submit_btn = gr.Button("发送", variant="primary", scale=1, min_width=80)

            with gr.Row():
                clear_btn = gr.Button("清除对话", size="sm", variant="secondary")
                session_display = gr.Textbox(
                    label="会话 ID",
                    interactive=False,
                    scale=3,
                    max_lines=1,
                )

        # 右侧：作业状态
        with gr.Column(scale=2):
            gr.Markdown("### 作业状态查询")

            job_id_input = gr.Textbox(
                label="Flink 作业 ID",
                placeholder="输入 32 位 hex 作业 ID，例如：a1b2c3d4...",
                max_lines=1,
            )
            query_btn = gr.Button("查询状态", variant="primary")
            job_status_output = gr.Markdown(
                value="输入作业 ID 后点击「查询状态」。\n\n"
                      "> 作业 ID 可以从对话中 Agent 的回复里获取，\n"
                      "> 或在 [Flink Web UI](http://localhost:8081) 中查看。",
            )

            gr.Markdown("---")
            gr.Markdown(
                """
                **提示**

                - 提交成功后，从 Agent 回复中复制作业 ID
                - 流式作业（datagen → PostgreSQL）会持续运行，状态为 RUNNING
                - 如需停止作业，直接在对话框中发送「停止作业 {作业ID}」
                """,
                elem_classes=["status-box"],
            )

    # ── Session 状态（Gradio State，用于跨请求共享） ──
    session_state = gr.State(value=str(uuid.uuid4())[:8])

    # ─────────────────────────────────────────────────────────
    # 事件绑定
    # ─────────────────────────────────────────────────────────

    # 发送消息
    submit_btn.click(
        fn=send_message,
        inputs=[msg_input, session_state, chatbot],
        outputs=[chatbot, msg_input, session_state],
    )
    msg_input.submit(
        fn=send_message,
        inputs=[msg_input, session_state, chatbot],
        outputs=[chatbot, msg_input, session_state],
    )

    # 清除对话（同时生成新 session_id，开启新对话）
    def clear_and_reset():
        new_sid = str(uuid.uuid4())[:8]
        return [], new_sid, new_sid  # 空列表对 Gradio 6.x Chatbot 没有格式要求

    clear_btn.click(
        fn=clear_and_reset,
        outputs=[chatbot, session_state, session_display],
    )

    # 查询作业状态
    query_btn.click(
        fn=query_job_status,
        inputs=[job_id_input],
        outputs=[job_status_output],
    )

    # 健康检查
    health_btn.click(fn=check_backend_health, outputs=[health_output])

    # 页面加载时同步 session_id 显示 + 检查后端
    demo.load(
        fn=lambda sid: (sid, check_backend_health()),
        inputs=[session_state],
        outputs=[session_display, health_output],
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        theme=gr.themes.Soft(
            primary_hue="slate",
            secondary_hue="slate",
            neutral_hue="slate",
        ),
    )
