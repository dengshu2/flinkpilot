# FlinkPilot

用自然语言驱动 Apache Flink 数据流的 AI Agent 平台。

```
你说：  帮我生成随机订单数据，按 10 秒窗口统计各城市 GMV，结果输出到控制台
Agent：  理解意图 → 生成 SQL → EXPLAIN 验证 → 提交作业 → 返回 Job ID
```

**技术栈**：Flink 2.2 · LangGraph 1.0 · FastAPI · Gradio · PostgreSQL · Docker Compose

**当前进度**：Phase 1 ✅ 已完成 — 核心链路跑通（SQL 生成 → 验证 → 修复循环 → 提交 → 监控）

---

## 它能做什么

FlinkPilot 不是 Flink 的遥控器，而是 **Flink 的副驾驶**。

| 传统方式 | FlinkPilot |
|---------|-----------|
| 手写 Flink SQL 或 DataStream 代码 | 自然语言描述意图，Agent 自动生成 |
| 提交前手动检查语法 | Agent 用 EXPLAIN 自动验证，失败自动修复（最多 3 次） |
| 手动提交、查看作业状态 | Agent 自动提交并返回 Job ID |
| 作业失败后翻日志找原因 | Agent 拉取异常日志并给出诊断建议 |
| 停止作业前无确认 | 高风险操作（如停止作业）自动拦截并等待确认 |

---

## 快速开始

### 前置条件

- Docker 和 Docker Compose
- 一个 LLM API Key（推荐 [OpenRouter](https://openrouter.ai)，支持 DeepSeek/Claude 等模型）
- [uv](https://docs.astral.sh/uv/)（Python 包管理，替代 pip）

### 启动步骤

```bash
# 1. 克隆仓库
git clone https://github.com/dengshu2/flinkpilot.git && cd flinkpilot

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 LLM_API_KEY

# 3. 启动基础设施（Flink + SQL Gateway + PostgreSQL）
docker compose up -d

# 4. 等待所有服务健康（约 30-60 秒）
docker compose ps

# 5. 安装后端依赖并启动
cd backend
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload &

# 6. 启动 Gradio 前端
uv run python gradio_app.py
```

### 访问地址

| 服务 | 地址 |
|------|------|
| Gradio 对话界面 | http://localhost:7860 |
| Agent API | http://localhost:8000 |
| Flink Web UI | http://localhost:8081 |
| SQL Gateway | http://localhost:8083 |

---

## 架构概览

```
┌─────────────────────────────────────────────────────┐
│                    用户界面层                          │
│     Gradio MVP（对话 + 作业状态查询 + 健康检查）        │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────┐
│               Agent 核心层（Python）                  │
│  FastAPI + LangGraph 1.0（ReAct 循环 + 状态持久化）   │
│                                                      │
│  Tools: validate_sql → submit_sql_job →              │
│         get_job_status → get_job_exceptions →         │
│         kill_job（human-in-the-loop）                 │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                    基础设施层                          │
│  Flink 2.2（JobManager + TaskManager + SQL Gateway） │
│  PostgreSQL 15（业务数据 + LangGraph 状态持久化）      │
└─────────────────────────────────────────────────────┘
```

### Agent 状态图

```
用户输入 → agent（LLM 推理）
              ↓ 选择 Tool
           tools（执行）
              ↓
        route_after_tools
           ├─ validate_sql 失败且重试 < 3 → 注入错误信息 → 回 agent 重试
           ├─ validate_sql 失败且重试 ≥ 3 → 报告失败并结束
           ├─ kill_job 等高风险操作       → human_review（等待用户确认）
           └─ 其他                       → 回 agent 继续推理
```

---

## 项目结构

```
flinkpilot/
├── backend/                     # FastAPI + LangGraph Agent
│   ├── main.py                  # API 入口（HTTP + WebSocket）
│   ├── gradio_app.py            # Gradio MVP 前端
│   ├── agent/
│   │   ├── graph.py             # LangGraph 状态图定义
│   │   ├── tools/
│   │   │   └── flink_tools.py   # Flink SQL 操作 Tools
│   │   └── prompts/
│   │       └── system_prompt.md # Agent 系统提示词
│   ├── pyproject.toml           # 依赖声明（uv 管理）
│   └── uv.lock                  # 依赖锁定文件
├── flink-conf/
│   └── config.yaml              # Flink 2.x 配置（YAML 格式）
├── docker-compose.yml           # 基础设施编排
├── docs/                        # 项目文档（见下方导航）
└── .env.example                 # 环境变量模板
```

---

## 文档

| 内容 | 位置 |
|------|------|
| 产品定位与竞品分析 | [docs/01-vision/](./docs/01-vision/) |
| 架构设计 | [docs/02-architecture/](./docs/02-architecture/) |
| 技术决策记录（ADR） | [docs/03-decisions/](./docs/03-decisions/) |
| 部署与配置指南 | [docs/04-guides/](./docs/04-guides/) |
| 开发者指南 | [docs/05-development/](./docs/05-development/) |
| 路线图与进度 | [docs/06-roadmap/](./docs/06-roadmap/) |

---

## 路线图

| 阶段 | 目标 | 状态 |
|------|------|------|
| **Phase 1** | 核心链路：自然语言 → SQL 生成 → 验证修复 → 提交 → 监控 | ✅ 已完成 |
| **Phase 2** | JAR 打包：LLM 生成 Java 代码 → Maven 构建 → 部署 | 待开始 |
| **Phase 3** | 产品化 UI：Vue 3 替换 Gradio，WebSocket 流式输出，DAG 可视化 | 待开始 |
| **Phase 4** | 高阶能力：Materialized Tables、ML_PREDICT、告警集成 | 待开始 |

详见 [phases.md](./docs/06-roadmap/phases.md) 和 [progress.md](./docs/06-roadmap/progress.md)。

---

## 关键技术决策

| 决策 | 选择 | 理由 | 文档 |
|------|------|------|------|
| Flink 版本 | 2.2 | 最新稳定版，新 YAML 配置，Materialized Table 生产就绪 | [ADR-001](./docs/03-decisions/ADR-001-flink-version.md) |
| Agent 框架 | LangGraph 1.0 | 多步骤 ReAct 循环，Durable State，human-in-the-loop | [ADR-002](./docs/03-decisions/ADR-002-langgraph.md) |
| SQL 提交模式 | Session Mode（MVP） | 轻量无依赖，后续按需迁移 Kyuubi | [ADR-003](./docs/03-decisions/ADR-003-sql-gateway-mode.md) |

---

## 贡献

欢迎提交 Issue 和 Pull Request。

开发前请阅读 [backend-dev.md](./docs/05-development/backend-dev.md) 了解代码规范和本地开发流程。

## 许可证

[MIT](./LICENSE)
