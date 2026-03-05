# 前端开发指南

> 上次更新：2026-03-05
> Phase 1 用 Gradio，Phase 3 切换为 Vue 3

---

## Phase 1：Gradio MVP

Phase 1 的目标是用最少时间验证 Agent 核心链路，前端选用 Gradio（1 天可搭建完成）。

### 安装

Gradio 已在 `requirements.txt` 中：

```bash
# 在 backend/requirements.txt 中添加
gradio>=5.0.0
```

### Phase 1 最小化前端

创建 `backend/gradio_app.py`：

```python
import gradio as gr
import httpx
import asyncio
import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

async def chat(message: str, session_id: str, history: list):
    """通过 WebSocket 与 Agent 通信，流式接收响应"""
    response_text = ""
    history.append((message, ""))

    async with httpx.AsyncClient() as client:
        # 简化版：使用 HTTP 接口（WebSocket 版见 backend main.py）
        resp = await client.post(
            f"{BACKEND_URL}/chat",
            json={"message": message, "session_id": session_id},
            timeout=60.0
        )
        async for chunk in resp.aiter_text():
            response_text += chunk
            history[-1] = (message, response_text)
            yield history, history

with gr.Blocks(title="FlinkPilot MVP") as demo:
    gr.Markdown("## FlinkPilot — 自然语言驱动 Flink 作业")
    gr.Markdown("描述你想要的流处理任务，Agent 会自动生成 SQL 并提交。")

    session_id = gr.State(value="default-session")

    chatbot = gr.Chatbot(label="对话", height=500)
    msg = gr.Textbox(
        placeholder="例如：用 datagen 生成随机用户行为数据，每10秒统计一次 PV 和 UV，写入 PostgreSQL",
        label="你的需求",
    )
    submit_btn = gr.Button("提交", variant="primary")
    clear_btn = gr.Button("清除对话")

    submit_btn.click(
        fn=chat,
        inputs=[msg, session_id, chatbot],
        outputs=[chatbot, chatbot],
    )
    msg.submit(
        fn=chat,
        inputs=[msg, session_id, chatbot],
        outputs=[chatbot, chatbot],
    )
    clear_btn.click(fn=lambda: [], outputs=[chatbot])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
```

### 启动

```bash
cd backend
python gradio_app.py
# 打开 http://localhost:7860
```

---

## Phase 3：Vue 3 正式前端

> 依赖 Phase 2 完成后启动，此处为预研参考。

### 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 框架 | Vue 3 + Vite | 轻量，WebSocket 友好，无 SSR 需求 |
| 路由 | Vue Router 4 | 官方标配 |
| 状态 | Pinia | 官方推荐，比 Vuex 简洁 |
| DAG 可视化 | AntV X6 | 只读 DAG 渲染，API 友好 |
| HTTP/WS | 原生 WebSocket + fetch | 不引入多余依赖 |

### 初始化项目

```bash
cd /root/projects/flinkpilot
npx -y create-vite@latest frontend -- --template vue
cd frontend
npm install
```

### 核心组件规划

```
frontend/src/
├── components/
│   ├── ChatPanel.vue      # 对话框，WebSocket 流式展示 Agent 推理
│   ├── JobList.vue        # 作业列表，轮询 Flink REST API 状态
│   └── DagViewer.vue      # AntV X6 只读 DAG，接收 Agent 输出的 JSON
├── views/
│   └── Dashboard.vue      # 主页面，组合以上组件
├── stores/
│   ├── session.js         # 会话管理（sessionId 持久化到 localStorage）
│   └── jobs.js            # 作业状态管理
└── api/
    └── agent.js           # WebSocket 封装，自动重连
```

### WebSocket 连接示例

```javascript
// frontend/src/api/agent.js
export class AgentSocket {
  constructor(sessionId) {
    this.sessionId = sessionId;
    this.ws = null;
    this.onMessage = null;
  }

  connect() {
    const wsUrl = `ws://localhost:8000/ws/chat/${this.sessionId}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onmessage = (event) => {
      if (this.onMessage) this.onMessage(event.data);
    };

    this.ws.onclose = () => {
      // 3 秒后自动重连
      setTimeout(() => this.connect(), 3000);
    };
  }

  send(message) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(message);
    }
  }
}
```

### Nginx 配置（Phase 3 部署）

```nginx
# 前后端同域名，避免 CORS 问题
server {
    listen 80;

    # 前端静态文件
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # 后端 API
    location /api/ {
        proxy_pass http://backend:8000/;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://backend:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;    # WebSocket 长连接
    }
}
```

---

## 注意事项

- **Phase 1 不要在前端上投入超过 1 天**，Gradio 够用就行
- Vue 3 前端只在 Phase 3 开始时初始化，过早创建会增加维护负担
- DAG 可视化（AntV X6）是**只读渲染**，不需要拖拉拽，保持简单
