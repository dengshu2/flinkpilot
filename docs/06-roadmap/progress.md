# FlinkPilot 开发进度

> 上次更新：2026-03-06（00:05）
> 当前阶段：**Phase 1**（Week 1–2，核心链路跑通）
> 整体进度：**Phase 1 全部完成** ✅

---

## 快速状态

| Phase | 名称 | 状态 | 完成度 |
|-------|------|------|--------|
| Phase 1 | 核心链路跑通（Week 1–2） | ✅ **已完成** | **9 / 9 任务** |
| Phase 2 | JAR 打包能力（Week 3–4） | ⚪ 未开始 | — |
| Phase 3 | 产品化 Web UI（Month 2） | ⚪ 未开始 | — |
| Phase 4 | 高阶能力（持续迭代） | ⚪ 未开始 | — |

---

## Phase 1：核心链路跑通

**验收标准**：datagen → Flink 窗口聚合 → PostgreSQL 端到端流程跑通（不依赖 Kafka）

### 基础设施准备

- [x] `flink-conf/config.yaml` 创建并验证（三个 Flink 容器均可正常加载）
- [x] `docker-compose.yml` 启动验证（所有服务正常 up）
- [x] Flink Web UI 可访问（http://localhost:8081）
- [x] SQL Gateway 可访问（http://localhost:8083）
- [x] PostgreSQL 连通性验证

### Agent 后端

- [x] `backend/` 目录初始化（FastAPI + requirements.txt）
- [x] LangGraph 图骨架搭建（`backend/agent/graph.py`，含 PostgresSaver 接入）
- [x] `generate_flink_sql` Tool 实现（调用 LLM，返回 SQL 字符串；含 previous_error 参数支持修复循环）
- [x] `validate_sql` Tool 实现（EXPLAIN 验证 + 报错信息解析）
- [x] `submit_sql_job` Tool 实现（含 Session 失效检测 + 自动重建）
- [x] `get_job_status` Tool 实现（轮询 Flink REST API）
- [x] SQL 生成 → 验证 → 修复循环接入 LangGraph 图（最多 3 次重试，handle_validate_failure 节点 + last_sql_error 注入 System Prompt）

### 前端 MVP

- [x] Gradio 界面搭建（`backend/gradio_app.py`：对话框 + 作业状态查询面板 + 后端健康检查）

### 端到端验收

- [x] datagen → 窗口聚合 SQL → PostgreSQL 完整流程跑通
- [x] Agent 可以从自然语言生成该 SQL 并提交成功（冒烟测试通过：Agent 正确生成 datagen + TUMBLE 窗口聚合 + PRINT/PostgreSQL 输出的完整 Flink 2.2 SQL）

---

## Phase 2：JAR 打包能力

> 依赖 Phase 1 完成后启动

### 任务列表

- [ ] `generate_java_code` Tool 实现（LLM 生成 DataStream Java 代码，指定 API V2 风格）
- [ ] Maven 构建容器搭建（Docker in Docker 或独立构建服务）
- [ ] `build_jar` Tool 实现（在构建容器内执行 Maven 打包）
- [ ] `deploy_jar` Tool 实现（上传 JAR 到 Flink REST API + 提交）
- [ ] 编译失败自动修复循环（报错 → 送回 LLM → 重新生成 → 重试）
- [ ] 与 Phase 1 的 Gradio UI 集成，支持 JAR 模式提交

---

## Phase 3：产品化 Web UI

> 依赖 Phase 2 完成后启动，且需提前明确商业模式（见下方决策点）

### 前置决策（Phase 2 结束前必须明确）

- [ ] **商业模式确认**：To-C 订阅 / To-B 私有化 / 开源项目（影响 UI 设计重点）
- [ ] **资源隔离方案确认**：评估 FLIP-316 进展，决定是否引入 Kyuubi（参考 [ADR-003](../03-decisions/ADR-003-sql-gateway-mode.md)）

### 任务列表

- [ ] Vue 3 + Vite 前端初始化
- [ ] WebSocket 连接 Agent 后端
- [ ] ChatPanel 组件（对话流，流式展示 Agent 推理过程）
- [ ] JobList 组件（作业列表 + 状态）
- [ ] DagViewer 组件（AntV X6，只读 DAG，Agent 输出 JSON → 渲染）
- [ ] Agent 主动监控：Backpressure 检测
- [ ] 异常推送（页面 toast / 通知）
- [ ] 接入 Grafana 监控 Dashboard（复用现有 ClickHouse + Grafana 栈）
- [ ] Gradio 下线，切换为正式 Vue 前端

---

## Phase 4：高阶能力

> 持续迭代，无固定时间节点

- [ ] Materialized Tables DDL 生成支持（Flink 2.2 已生产就绪，可提前纳入）
- [ ] ML_PREDICT TVF 集成（Flink SQL 内原生调用 LLM，Phase 4 差异化功能）
- [ ] 作业版本管理与回滚
- [ ] 告警集成（钉钉 / 飞书 Webhook）
- [ ] flink-agents 官方框架集成评估（作为 Tool 层）

---

## 重要决策记录（快速索引）

| 决策事项 | 状态 | 文档 |
|---------|------|------|
| Flink 版本选型 | ✅ 已确定（Flink 2.2） | [ADR-001](../03-decisions/ADR-001-flink-version.md) |
| Agent 框架选型 | ✅ 已确定（LangGraph 1.0） | [ADR-002](../03-decisions/ADR-002-langgraph.md) |
| SQL Gateway 模式 | ✅ 已确定（分阶段：Session → Kyuubi） | [ADR-003](../03-decisions/ADR-003-sql-gateway-mode.md) |
| 商业模式 | ❓ 待定（Phase 2 结束前需确认） | — |
| Kyuubi 引入时机 | ❓ 待定（Phase 3 前评估） | [ADR-003](../03-decisions/ADR-003-sql-gateway-mode.md) |

---

## 已知风险与跟进项

| 风险 | 优先级 | 状态 |
|------|--------|------|
| LLM 生成 Flink 2.x SQL 语法准确率 | 🔴 高 | Phase 1 通过修复循环缓解 |
| Connector JAR 版本兼容性 | 🔴 高 | 已在文档中明确，部署前必须验证 |
| SQL Gateway Session 失效处理 | 🟡 中 | Phase 1 在 Tool 层实现检测和重建 |
| FLIP-316 进展（SQL Gateway Application mode） | 🟡 中 | Phase 3 前重新评估 |

---

## 更新记录

| 日期 | 变更内容 |
|------|---------|
| 2026-03-05 | 架构文档完成，docs 结构初始化，进度追踪建立 |
| 2026-03-05 | 补全所有缺失文档（local-setup、sql-prompt-guide、frontend-dev、llm-api-config、docker-compose.yml、.env.example），git init 完成首个 commit（a5decc8），开发就绪 |
| 2026-03-05 | Phase 1 基础设施全部跑通。修复 docker-compose 两个关键问题：①单文件挂载 config.yaml（避免覆盖镜像默认 conf）；②移除 flink-lib→/opt/flink/lib 空目录挂载（避免覆盖核心 JAR）。Flink 2.2.0 + SQL Gateway + PostgreSQL 15 健康。backend/ 骨架完成：main.py、agent/graph.py（LangGraph 1.0 + PostgresSaver + human-in-the-loop）、agent/tools/flink_tools.py（4 个 Phase 1 Tool）、agent/prompts/system_prompt.md |
| 2026-03-05 | Phase 1 所有代码实现完成。① `generate_flink_sql` Tool（LLM 调用，Markdown 代码块提取，支持 previous_error 修复参数）。② `graph.py` 重构：新增 `last_sql_error` State 字段、`handle_validate_failure` 节点、`route_after_tools` 中 validate_sql 失败路由，错误信息注入 System Prompt 引导 LLM 修复（最多 3 次）。③ `backend/gradio_app.py`：Gradio 5.x MVP 前端，对话框 + 作业状态查询 + 健康检查。④ `main.py` 新增 `/api/jobs/{job_id}` 和 `/api/jobs` 代理端点。⑤ `requirements.txt` 添加 httpx、升级 gradio>=5.0.0。待执行：端到端联调验收。|
| 2026-03-06 | **Phase 1 全部完成**。端到端冗烟测试通过：Agent 自动生成 datagen + TUMBLE 窗口聚合 + PRINT 输出的完整 Flink 2.2 SQL（Watermark、CREATE TEMPORARY TABLE、INSERT INTO 全部正确）。修复运行层问题：AsyncPostgresSaver（LangGraph 1.0.10 新 API）、容器内部域名 vs localhost 地址问题（backend/.env.local 覆盖）、Gradio 6.x API 小变更。项目就绪 Phase 2。 |
