# FlinkPilot — Flink AI Agent 平台技术架构方案

> **约束**：单台 VPS + 一个 LLM API（OpenAI / Claude / 国内模型均可）
> **目标**：用自然语言驱动 Flink 数据流，而不是代码和配置
> **版本**：2026-03-05（基于 Flink 2.x / LangGraph 1.0）

---

## 一、产品定位

**不是"Flink 的遥控器"，而是"Flink 的副驾驶"**

```
用户说：帮我从 Kafka 读用户点击数据，按 5 分钟窗口统计 PV，写入 PostgreSQL
Agent：  理解意图 → 生成 SQL → 验证 → 提交 → 监控 → 异常诊断
```

| 维度 | 传统拖拉拽平台 | 本方案 |
|------|--------------|-------|
| 输入方式 | 手动拖拽节点、填参数 | 自然语言描述意图 |
| 可视化 | 输入层（用户操作） | 结果层（AI 生成后展示） |
| 作业监控 | 被动查看 | Agent 主动推送 + 诊断建议 |
| 定位 | 2018–2022 范式 | 2025–2026 范式 |

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────┐
│                    用户界面层                          │
│     Web UI（MVP: Gradio → 产品化: Vue 3）             │
│     对话框 + DAG 可视化（只读）+ 作业列表 + 监控面板    │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼──────────────────────────────┐
│               Agent 核心层（Python）                  │
│           FastAPI + LangGraph 1.0                    │
│                                                      │
│  ┌─────────────────┐  ┌──────────┐  ┌─────────────┐ │
│  │  对话管理        │  │  LLM 调用 │  │  Tool 路由  │ │
│  │ (Durable State) │  │ (你的API) │  │  (Skills)   │ │
│  └─────────────────┘  └──────────┘  └─────────────┘ │
└──────────────────────┬──────────────────────────────┘
                       │ 调用各种 Tool / Skill
┌──────────────────────▼──────────────────────────────┐
│                    基础设施层                          │
│  Flink 2.2 Standalone │ SQL Gateway │ PostgreSQL     │
│  Maven 构建服务        │ Nginx       │ 构建产物存储   │
│      （Docker Compose 编排，运行在同一台 VPS）         │
└─────────────────────────────────────────────────────┘
```

---

## 三、技术栈选型

### 3.1 Agent 框架：LangGraph 1.0

Flink 场景是典型的多步骤 ReAct 循环（理解意图 → 生成 SQL → 提交 → 监控 → 诊断），LangGraph 原生支持。

**LangGraph 1.0 的关键新特性对本项目有直接价值：**

- **Durable State**：Agent 执行状态自动持久化到 PostgreSQL，VPS 重启后长流程（如生成 → 打包 → 部署）可从断点续跑，无需自己维护 checkpoint 逻辑
- **Built-in Persistence**：会话历史天然存储，省去大量 DB 模板代码
- **Human-in-the-loop**：在执行高风险操作（如 kill job）前暂停等待用户确认

```bash
pip install langgraph langchain-openai fastapi uvicorn
```

`requirements.txt` 中注意 psycopg 版本，LangGraph 1.0 推荐 psycopg3，而非 psycopg2：

```
langgraph>=1.0.0
langchain-openai>=0.3.0
fastapi
uvicorn
psycopg[binary]>=3.1.0   # ← 注意：是 psycopg3，不是 psycopg2-binary
```

### 3.2 核心 Skills（Tool 设计）

```python
from langchain_core.tools import tool
import requests

@tool
def generate_flink_sql(description: str) -> str:
    """根据用户描述生成 Flink SQL"""
    ...

@tool
def validate_sql(sql: str, session_id: str) -> dict:
    """用 Flink EXPLAIN 验证 SQL 语法"""
    resp = requests.post(
        f"http://flink-sql-gateway:8083/v1/sessions/{session_id}/statements",
        json={"statement": f"EXPLAIN {sql}"}
    )
    return resp.json()

@tool
def submit_sql_job(sql: str, session_id: str) -> dict:
    """通过 Flink SQL Gateway 提交 SQL 作业（无需 JAR）"""
    resp = requests.post(
        f"http://flink-sql-gateway:8083/v1/sessions/{session_id}/statements",
        json={"statement": sql}
    )
    return resp.json()

@tool
def get_job_metrics(job_id: str) -> dict:
    """获取作业指标：TPS、延迟、Backpressure"""
    resp = requests.get(f"http://flink-jobmanager:8081/jobs/{job_id}/metrics")
    return resp.json()

@tool
def get_job_exceptions(job_id: str) -> str:
    """获取作业异常日志，用于诊断问题"""
    ...

@tool
def kill_job(job_id: str) -> dict:
    """停止指定作业（执行前触发 human-in-the-loop 确认）"""
    ...
```

### 3.3 后端：FastAPI + WebSocket

```python
from fastapi import FastAPI, WebSocket
from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres import PostgresSaver

app = FastAPI()

# LangGraph 1.0：用 PostgreSQL 做持久化 checkpointer
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

### 3.4 前端选型

| 阶段 | 方案 | 工作量 |
|------|------|--------|
| MVP 验证期 | **Gradio** | 1 天，快速跑通核心链路 |
| 产品化 | **Vue 3 + Vite** | 3–5 天，支持 WebSocket，轻量 |

**DAG 可视化**：AntV X6（中文文档友好），Agent 输出 JSON → 前端只读渲染，不需要拖拉拽。

> 当有 SEO 需求或用户规模增长时，再考虑迁移到 Next.js。

---

## 四、Flink 版本说明（重要）

**推荐使用 Flink 2.2**，不要使用 1.18。主要差异：

| 项目 | Flink 1.18 | Flink 2.2 |
|------|-----------|-----------|
| Java 要求 | Java 8+ | **Java 11+**（8 已移除） |
| Per-job 模式 | 支持 | **已移除**，改用 Application mode |
| SQL Gateway Application Mode | 不支持 | **已支持**，解决 Session mode 资源隔离问题 |
| AI 集成 | 无 | ML_PREDICT（Flink SQL 内调用 LLM）|
| Materialized Tables | 无 | **生产可用**，流批统一声明式管道 |

**Session mode 的隐患**（MVP 阶段需知晓）：SQL Gateway 默认跑在 Session mode，多个作业共享同一批 TaskManager——一个作业 OOM 会影响其他作业。MVP 阶段可以接受。

产品化阶段的资源隔离有两条路，**不是**简单切换 Application mode（SQL Gateway 的 Application mode 原生支持在 Flink 2.x 中仍不完整）：

| 方案 | 难度 | 说明 |
|------|------|------|
| **Apache Kyuubi 中间层** | 中 | 开源项目，支持 Flink Application mode + 多租户，推荐 |
| SQL 封装成 JAR 提交 | 高 | 绕过 SQL Gateway，直接走 REST API 提交 JSON Plan |

---

## 五、VPS 部署方案

### 5.1 Docker Compose

```yaml
# docker-compose.yml
services:
  flink-jobmanager:
    image: flink:2.2          # ← 使用 Flink 2.2
    ports:
      - "8081:8081"
    command: jobmanager
    volumes:
      - ./flink-lib:/opt/flink/lib      # ← 挂载 connector JARs（见下方说明）
      - ./flink-conf/config.yaml:/opt/flink/conf/config.yaml  # ← Flink 2.x 使用 config.yaml

  flink-taskmanager:
    image: flink:2.2
    depends_on: [flink-jobmanager]
    command: taskmanager
    volumes:
      - ./flink-lib:/opt/flink/lib
      - ./flink-conf/config.yaml:/opt/flink/conf/config.yaml
    deploy:
      resources:
        limits:
          memory: 1G            # VPS 内存紧张时可调为 512M

  flink-sql-gateway:
    image: flink:2.2
    ports:
      - "8083:8083"
    depends_on: [flink-jobmanager]
    command: sql-gateway.sh start-foreground
    volumes:
      - ./flink-lib:/opt/flink/lib
      - ./flink-conf/config.yaml:/opt/flink/conf/config.yaml

  agent-backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_BASE_URL=${LLM_BASE_URL}
      - FLINK_REST_URL=http://flink-jobmanager:8081
      - FLINK_SQL_GATEWAY_URL=http://flink-sql-gateway:8083
      - DATABASE_URL=postgresql://postgres:secret@db:5432/flinkpilot

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: flinkpilot
      POSTGRES_PASSWORD: secret
    volumes:
      - postgres_data:/var/lib/postgresql/data

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on: [agent-backend, frontend]

volumes:
  postgres_data:
```

Flink 2.x 废弃了旧的 `flink-conf.yaml`，需要手动创建 `./flink-conf/config.yaml`：

```yaml
# flink-conf/config.yaml（Flink 2.x 新格式，严格遵循 YAML 标准）
jobmanager:
  rpc:
    address: flink-jobmanager
  memory:
    process:
      size: 1600m

taskmanager:
  memory:
    process:
      size: 1728m

sql-gateway:
  endpoint:
    rest:
      address: 0.0.0.0
```

### 5.2 Connector JARs 准备（必须）

官方 Flink 镜像**不包含** Kafka / JDBC 等 connector，需要提前下载并挂载。

> ⚠️ **版本必须匹配 Flink 2.x**。Flink 2.0 移除了旧的 `SourceFunction` / `SinkFunction` 接口，使用后缀为 `-1.19`、`-1.20` 的旧版 JAR 会在运行时报 `ClassNotFoundException`，且错误信息不直观，极难排查。

```bash
mkdir -p ./flink-lib

# Kafka connector（面向 Flink 2.x 的兼容版）
wget -P ./flink-lib \
  https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/4.0.0-2.0/flink-sql-connector-kafka-4.0.0-2.0.jar

# JDBC connector（面向 Flink 2.x）
wget -P ./flink-lib \
  https://repo.maven.apache.org/maven2/org/apache/flink/flink-connector-jdbc/4.0.0-2.0/flink-connector-jdbc-4.0.0-2.0.jar

# PostgreSQL JDBC 驱动（版本无关 Flink，保持最新即可）
wget -P ./flink-lib \
  https://jdbc.postgresql.org/download/postgresql-42.7.3.jar
```

> ⚠️ 如版本号有变化，可在 [https://repo.maven.apache.org/maven2/org/apache/flink/](https://repo.maven.apache.org/maven2/org/apache/flink/) 手动搜索确认最新的 2.x 兼容版本后再下载。

### 5.3 内存估算

| 服务 | 内存占用 |
|------|---------|
| Flink JobManager | ~512 MB |
| Flink TaskManager × 1 | ~1 GB |
| Flink SQL Gateway | ~256 MB |
| Agent Backend (Python) | ~256 MB |
| PostgreSQL | ~128 MB |
| Nginx + 前端 | ~64 MB |
| **合计** | **~2.2 GB** |

4G 内存 VPS 完全够用；2G VPS 将 TaskManager 堆限制到 512M，也能跑。

---

## 六、分阶段落地路线

### Phase 1：核心链路跑通（Week 1–2）

**目标**：用户说需求 → Agent 生成 SQL → 提交 → 看到结果

Skills：`generate_flink_sql` / `validate_sql` / `submit_sql_job` / `get_job_status`

前端：Gradio，1 天搞定

**Phase 1 必须实现的两个工程细节：**

**① SQL 生成 → 验证 → 修复循环**：不能依赖 LLM 单次生成直接提交。Flink SQL 的 watermark 语法、Window TVF 写法在 Flink 2.x 有细微变化，LLM 训练数据以 1.x 风格为主，生成的 SQL 可能存在语法错误。正确的流程是：

```
generate_sql → validate_sql（EXPLAIN）→ 失败 → 把报错信息送回 LLM → 重新生成 → 重试（最多 3 次）
```

**② SQL Gateway Session 失效处理**：Gateway Session 属性存储在内存中，重启后失效。`submit_sql_job` Tool 需要内置 Session 有效性检测，失效时自动重建：

```python
@tool
def submit_sql_job(sql: str, session_id: str) -> dict:
    """提交 SQL 作业，自动处理 Session 失效"""
    # 先检测 Session 是否有效
    check = requests.get(f"{GATEWAY_URL}/v1/sessions/{session_id}")
    if check.status_code != 200:
        # Session 失效，重新创建
        new_session = requests.post(f"{GATEWAY_URL}/v1/sessions").json()
        session_id = new_session["sessionHandle"]
    resp = requests.post(
        f"{GATEWAY_URL}/v1/sessions/{session_id}/statements",
        json={"statement": sql}
    )
    return {**resp.json(), "session_id": session_id}
```

**验收标准**：能完整跑通 datagen → Flink 窗口聚合 → PostgreSQL 端到端流程（不依赖 Kafka）

#### 测试数据源：datagen connector

Week 1 **不需要启动 Kafka**，用 Flink 官方内置的 `datagen` connector 直接在内存中生成数据，省资源、省调试时间，专注验证 Agent 链路本身。

```sql
-- 模拟用户点击事件，零依赖，开箱即用
CREATE TABLE user_clicks (
    user_id    INT,
    page_id    INT,
    click_time TIMESTAMP(3),
    WATERMARK FOR click_time AS click_time - INTERVAL '5' SECOND
) WITH (
    'connector'                  = 'datagen',
    'rows-per-second'            = '100',
    'fields.user_id.kind'        = 'random',
    'fields.user_id.min'         = '1',
    'fields.user_id.max'         = '10000',
    'fields.page_id.kind'        = 'random',
    'fields.page_id.min'         = '1',
    'fields.page_id.max'         = '500',
    'fields.click_time.max-past' = '5000'
);

-- 窗口聚合写入 PostgreSQL（这就是 Agent 要生成并提交的 SQL）
INSERT INTO pv_result
SELECT
    page_id,
    COUNT(*)                                              AS pv,
    TUMBLE_START(click_time, INTERVAL '5' MINUTE)        AS window_start
FROM user_clicks
GROUP BY page_id, TUMBLE(click_time, INTERVAL '5' MINUTE);
```

> `datagen` 是 Flink 内置 connector，**无需下载任何 JAR**，JobManager / TaskManager / SQL Gateway 镜像均自带。

**后续阶段的数据源演进**：

| 阶段 | 数据源 | 说明 |
|------|--------|------|
| Week 1–2 | `datagen`（内置） | 零依赖，专注验证 Agent 链路 |
| Phase 2 | `datagen → Kafka → Flink` | 用 Flink SQL 作业往 Kafka 写数据，再消费，不需要额外 producer 程序 |
| Phase 3+ | 真实业务数据 | 接入实际 Kafka topic |

---

### Phase 2：JAR 打包能力（Week 3–4）

- `generate_java_code`：LLM 生成 DataStream Java 代码
- `build_jar`：Docker 容器内 Maven 打包，隔离依赖
- `deploy_jar`：上传 JAR 到 Flink REST API 并提交

---

### Phase 3：产品化（Month 2）

- 替换 Gradio → Vue 3 正式 Web UI
- DAG 可视化（AntV X6，只读展示）
- Agent 主动监控：Backpressure 检测 + 异常推送
- 监控 Dashboard 复用现有 ClickHouse + Grafana 栈

---

### Phase 4：高阶能力（持续迭代）

- **Materialized Tables 支持**：Agent 生成声明式 DDL，流批统一，降低用户学习成本
- 作业版本管理与回滚
- 告警集成（钉钉 / 飞书）
- 跟进 Flink-Agents 0.1 框架（官方已于 2025 年发布）

---

## 七、项目目录结构

```
flinkpilot/
├── docker-compose.yml
├── .env                          # LLM_API_KEY 等
├── flink-lib/                    # ← Connector JARs（挂载到 Flink 容器）
│   ├── flink-sql-connector-kafka-*.jar
│   ├── flink-connector-jdbc-*.jar
│   └── postgresql-*.jar
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                   # FastAPI 入口
│   └── agent/
│       ├── graph.py              # LangGraph 状态图（含 PostgresSaver）
│       ├── tools/
│       │   ├── flink_tools.py
│       │   ├── build_tools.py
│       │   └── monitor_tools.py
│       └── prompts/
│           └── system_prompt.md
│
├── frontend/                     # MVP 阶段可暂缺，用 Gradio 替代
│   └── src/
│       ├── components/
│       │   ├── ChatPanel.vue
│       │   ├── DagViewer.vue     # 只读 DAG，AntV X6
│       │   └── JobList.vue
│       └── api/ws.js
│
└── nginx.conf
```

---

## 八、成本估算

| 项目 | 费用 |
|------|------|
| VPS（4C8G，Hetzner / 腾讯云轻量） | ¥50–200/月 |
| LLM API（日常开发 + 压测） | ¥50–200/月 |
| 域名 + SSL | ¥50–100/年 |
| **合计** | **约 ¥100–400/月** |

---

## 九、关键决策总结

| 要素 | 选择 | 理由 |
|------|------|------|
| Flink 版本 | **2.2** | Application mode、SQL Gateway 增强、AI 集成 |
| Agent 框架 | **LangGraph 1.0** | Durable State、multi-step ReAct、Human-in-the-loop |
| 后端 | **FastAPI** | 异步、轻量、Python 生态 |
| 数据库 | **PostgreSQL** | 兼做 LangGraph checkpointer，一库两用 |
| 前端（MVP） | **Gradio** | 1 天出 UI，快速验证 |
| 前端（产品化） | **Vue 3 + Vite** | 轻量，WebSocket 友好 |
| DAG 可视化 | **AntV X6** | 中文文档友好，只读渲染 |
| Flink 提交（MVP） | **SQL Gateway Session mode** | 跳过 JAR，最快路径 |
| Flink 提交（产品化） | **Kyuubi + Application mode** | 资源隔离，SQL Gateway 原生 Application mode 支持尚不完整 |
| 监控 | **ClickHouse + Grafana**（复用现有） | 无需另起炉灶 |
| 部署 | **Docker Compose** | 一键启动，VPS 友好 |

> **最重要的一句话**：先下载好 Connector JARs，用 SQL Gateway + Gradio 在 Week 1 跑通端到端链路；之后的一切复杂性，都可以增量叠加。
