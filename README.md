# FlinkPilot

> 用自然语言驱动 Flink 数据流的 AI Agent 平台。

```
用户说：帮我从 Kafka 读用户点击数据，按 5 分钟窗口统计 PV，写入 PostgreSQL
Agent：  理解意图 → 生成 SQL → 验证 → 提交 → 监控 → 异常诊断
```

**技术栈**：Flink 2.2 · LangGraph 1.0 · FastAPI · Vue 3 · PostgreSQL · Docker Compose

---

## 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url> && cd flinkpilot

# 2. 准备 Connector JARs（重要，版本必须匹配 Flink 2.x）
# 详见 docs/04-guides/connector-jars.md
mkdir -p ./flink-lib
wget -P ./flink-lib https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/4.0.0-2.0/flink-sql-connector-kafka-4.0.0-2.0.jar
wget -P ./flink-lib https://repo.maven.apache.org/maven2/org/apache/flink/flink-connector-jdbc/4.0.0-2.0/flink-connector-jdbc-4.0.0-2.0.jar
wget -P ./flink-lib https://jdbc.postgresql.org/download/postgresql-42.7.3.jar

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 和 LLM_BASE_URL

# 4. 启动所有服务
docker compose up -d

# 5. 访问
# Flink Web UI:   http://localhost:8081
# Agent API:      http://localhost:8000
# 前端（MVP）:    http://localhost:3000
```

---

## 项目结构

```
flinkpilot/
├── docker-compose.yml
├── flink-conf/
│   └── config.yaml              # Flink 2.x 配置（挂载到所有 Flink 容器）
├── flink-lib/                   # Connector JARs（需手动下载）
├── backend/                     # FastAPI + LangGraph Agent
│   ├── main.py
│   └── agent/
│       ├── graph.py             # LangGraph 状态图
│       ├── tools/               # Flink Tools
│       └── prompts/
├── frontend/                    # Vue 3 前端（MVP 阶段用 Gradio 替代）
├── docs/                        # 项目文档
└── nginx.conf
```

---

## 文档导航

| 想了解的内容 | 文档位置 |
|-------------|---------|
| 产品定位和竞品分析 | [docs/01-vision/](./docs/01-vision/) |
| 整体架构设计 | [docs/02-architecture/](./docs/02-architecture/) |
| 关键技术决策记录（ADR） | [docs/03-decisions/](./docs/03-decisions/) |
| 配置和部署操作 | [docs/04-guides/](./docs/04-guides/) |
| 开发者指南 | [docs/05-development/](./docs/05-development/) |
| 项目路线图 | [docs/06-roadmap/phases.md](./docs/06-roadmap/phases.md) |
| 完整架构文档（原始稿） | [flinkpilot_architecture.md](./flinkpilot_architecture.md) |

---

## 许可证

MIT
