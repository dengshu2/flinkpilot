# FlinkPilot — AI 开发上下文

> 这个文件是给 Antigravity（AI 编程助手）读的。
> 在开始任何开发任务前，必须先阅读本文件，然后按指引读取相关文档。

---

## 项目概述

FlinkPilot 是一个用自然语言驱动 Apache Flink 数据流的 AI Agent 平台。
核心链路：**用户自然语言输入 → LangGraph Agent → Flink SQL 生成/验证/提交 → 结果监控**

**当前进度**：见 [`docs/06-roadmap/progress.md`](../docs/06-roadmap/progress.md)
**当前阶段**：Phase 1 ✅ 已完成，准备开始 **Phase 2**（Week 3–4，JAR 打包能力）

---

## 开始任何任务前，必须阅读的文档

### 总是要读（每次）

| 文档 | 读的原因 |
|------|---------|
| [`docs/06-roadmap/progress.md`](../docs/06-roadmap/progress.md) | 了解当前进度，避免做已完成或已变更的事 |
| [`docs/06-roadmap/phases.md`](../docs/06-roadmap/phases.md) | 当前 Phase 的验收标准和优先级 |

### 按任务类型选读

| 任务类型 | 必读文档 |
|---------|---------|
| 首次启动 / 排查基础设施问题 | [`docs/04-guides/local-setup.md`](../docs/04-guides/local-setup.md) |
| 修改 Flink 配置 / Docker Compose | [`docs/04-guides/flink-config.md`](../docs/04-guides/flink-config.md) + [`docs/04-guides/local-setup.md`](../docs/04-guides/local-setup.md) |
| 添加/更新 Connector JAR | [`docs/04-guides/connector-jars.md`](../docs/04-guides/connector-jars.md) |
| 修改 Agent 核心逻辑 / LangGraph 图 | [`docs/02-architecture/agent-design.md`](../docs/02-architecture/agent-design.md) + [`docs/03-decisions/ADR-002-langgraph.md`](../docs/03-decisions/ADR-002-langgraph.md) |
| 讨论 Flink 版本或 SQL Gateway 模式 | [`docs/03-decisions/ADR-001-flink-version.md`](../docs/03-decisions/ADR-001-flink-version.md) + [`docs/03-decisions/ADR-003-sql-gateway-mode.md`](../docs/03-decisions/ADR-003-sql-gateway-mode.md) |
| 后端开发（新增 Tool / API） | [`docs/05-development/backend-dev.md`](../docs/05-development/backend-dev.md) |
| 前端开发 | [`docs/05-development/frontend-dev.md`](../docs/05-development/frontend-dev.md) |
| LLM Prompt 调优 | [`docs/05-development/sql-prompt-guide.md`](../docs/05-development/sql-prompt-guide.md) |

---

## 完成任务后，必须更新的文档

这是最容易被跳过的步骤，但也是最重要的。

### 规则：什么变了就更新什么

| 如果你做了… | 必须更新 |
|-----------|---------|
| 完成了 progress.md 中的某个 Task | `docs/06-roadmap/progress.md`（勾选对应任务） |
| 修改了 Docker Compose / Flink 配置 | `docs/04-guides/flink-config.md` 或 `local-setup.md` |
| 添加/修改了 Connector JAR | `docs/04-guides/connector-jars.md` |
| 新增了 LangGraph Tool / 修改 Agent 图 | `docs/02-architecture/agent-design.md` |
| 做了重要的技术决策（选型、放弃某方案） | 在 `docs/03-decisions/` 下新建或更新 ADR |
| 修改了 requirements.txt 依赖 | `docs/05-development/backend-dev.md` 中的依赖章节 |
| Phase 完成或里程碑达成 | `docs/06-roadmap/progress.md` + `CHANGELOG.md`（如有） |

---

## 关键技术约束（高频参考）

在生成代码时，以下约束必须严格遵守：

```
Flink 版本：2.2（最新稳定版）
Connector JAR 格式：必须是 *-2.x 后缀（面向 Flink 2.x），禁止使用 -1.19/-1.20
Flink 配置格式：config.yaml（YAML 嵌套格式），不是旧的 flink-conf.yaml 扁平格式
Python psycopg：psycopg[binary]>=3.1.0（psycopg3），不是 psycopg2-binary
LangGraph 版本：>=1.0.0（Durable State API）
SQL Gateway 模式：MVP 用 Session mode，产品化用 Kyuubi + Application mode
```

---

## 项目目录结构

```
flinkpilot/
├── .agents/                  # AI 助手上下文（你现在读的这里）
│   ├── CONTEXT.md            # 本文件
│   └── workflows/            # 常用操作流程
├── docs/                     # 项目文档
│   ├── 01-vision/            # 产品定位
│   ├── 02-architecture/      # 架构设计
│   ├── 03-decisions/         # ADR 决策记录
│   ├── 04-guides/            # 操作指南（部署/配置）
│   ├── 05-development/       # 开发者指南
│   └── 06-roadmap/           # 路线图和进度
├── backend/                  # FastAPI + LangGraph Agent
├── frontend/                 # Vue 3 前端
├── flink-conf/               # Flink 配置文件
├── flink-lib/                # Connector JARs（手动下载）
└── docker-compose.yml
```

---

## 不要做的事

- ❌ 不要生成使用 `psycopg2` 的代码，必须用 `psycopg`（psycopg3）
- ❌ 不要下载 `-1.19` 或 `-1.20` 后缀的 Connector JAR
- ❌ 不要用旧的 `FLINK_PROPERTIES` 环境变量注入方式，改用 `config.yaml` 挂载
- ❌ 不要在 `kill_job` 外的高风险操作上跳过 human-in-the-loop 确认
- ❌ 不要生成 LLM 单次直接提交 SQL 的代码，必须包含验证-修复循环
- ❌ 不要把多条 SQL 语句合并成一条发送给 SQL Gateway（每次只能发一条，须逐条提交）
- ❌ 不要把 `generate_flink_sql` 加回 `PHASE1_TOOLS`（会导致双重 LLM 调用使响应超时）

---

## Phase 1 已知问题（待后续 Phase 研究）

| 问题 | 现象 | 建议方向 |
|------|------|----------|
| `print` connector stdout 在 Web UI 不可见 | Docker standalone 模式下 Web UI 的 Stdout 选项卡显示 "file does not exist"；实际输出需通过 `docker logs flink-taskmanager` 查看 | 研究 `env.log.dir` / `taskmanager.log.path` Flink 配置；或搜索 "Flink Docker print connector stdout web ui" 有无官方解决方案；长期用 PostgreSQL sink 替代 print |
| `get_job_id` 竞争条件 | `submit_sql_job` 通过轮询 `/jobs/overview` 取最新 RUNNING 作业，多作业并发时可能拿到错误 job_id | 研究 SQL Gateway operation_handle → Flink job_id 的官方映射接口（`/v1/sessions/{s}/operations/{o}/result` 是否含 jobId 字段）|
| Session 单点 | SQL Gateway Session 重启后丢失所有 TEMPORARY TABLE，Agent 须重新建表 | Phase 2 评估 Application mode 替代 Session mode |
