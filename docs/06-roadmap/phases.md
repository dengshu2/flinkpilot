# Phase 1-4 落地路线图

> 核心原则：先跑通端到端链路，再叠加复杂度。

---

## Phase 1：核心链路跑通（Week 1–2）

**目标**：用户说需求 → Agent 生成 SQL → 提交 → 看到结果

**Skills**：`generate_flink_sql` / `validate_sql` / `submit_sql_job` / `get_job_status`

**前端**：Gradio（1 天搭建，快速验证核心链路）

### 验收标准

能完整跑通 `datagen → Flink 窗口聚合 → PostgreSQL` 端到端流程（不依赖 Kafka）

### 必须实现的两个工程细节

**① SQL 生成 → 验证 → 修复循环**

不能依赖 LLM 单次生成直接提交。正确流程：

```
generate_sql → validate_sql（EXPLAIN）→ 失败 → 报错信息送回 LLM → 重新生成 → 重试（最多 3 次）
```

**② SQL Gateway Session 失效处理**

Gateway Session 在内存中，重启后失效。Tool 需内置检测与重建逻辑：

```python
@tool
def submit_sql_job(sql: str, session_id: str) -> dict:
    check = requests.get(f"{GATEWAY_URL}/v1/sessions/{session_id}")
    if check.status_code != 200:
        new_session = requests.post(f"{GATEWAY_URL}/v1/sessions").json()
        session_id = new_session["sessionHandle"]
    resp = requests.post(
        f"{GATEWAY_URL}/v1/sessions/{session_id}/statements",
        json={"statement": sql}
    )
    return {**resp.json(), "session_id": session_id}
```

### Phase 1 数据源演进

| 时间 | 数据源 | 说明 |
|------|--------|------|
| Week 1 | `datagen`（Flink 内置） | 零依赖，专注验证 Agent 链路，**不需要 Kafka** |
| Week 2 | PostgreSQL sink 验证 | 确认端到端写入正确 |

---

## Phase 2：JAR 打包能力（Week 3–4）

**目标**：支持 LLM 生成 DataStream Java 代码并打包为 JAR 提交

**新增 Skills**：
- `generate_java_code`：LLM 生成 DataStream Java 代码（需在 Prompt 中明确指定 DataStream API V2 风格）
- `build_jar`：Docker 容器内 Maven 打包，隔离依赖
- `deploy_jar`：上传 JAR 到 Flink REST API 并提交

**关键挑战**：LLM 训练数据以 Flink 1.x 代码为主，生成的 Java 代码可能使用旧 API。需要在编译失败时将错误信息送回 LLM 重新生成（参考 Phase 1 的 SQL 修复循环模式）。

---

## Phase 3：产品化（Month 2）

**目标**：替换 Gradio，构建正式 Web UI

- 替换 Gradio → Vue 3 + Vite
- DAG 可视化（AntV X6，只读展示）
- Agent 主动监控：Backpressure 检测 + 异常推送
- 监控 Dashboard 复用现有 ClickHouse + Grafana 栈

**重要决策点**：在 Phase 3 开始前，需要明确商业模式（To-C 订阅 / To-B 私有化 / 开源），这直接影响 UI 设计重点和功能优先级。

**资源隔离升级**：评估是否引入 Kyuubi，参考 [ADR-003](../03-decisions/ADR-003-sql-gateway-mode.md)。

---

## Phase 4：高阶能力（持续迭代）

- **Materialized Tables 支持**：Agent 生成声明式 DDL，流批统一，降低用户学习成本（Flink 2.2 已生产就绪，可提前）
- **ML_PREDICT 集成**：Flink SQL 内原生调用 LLM，无需外部 API 调用（Flink 2.1+ 支持）
- 作业版本管理与回滚
- 告警集成（钉钉 / 飞书）
- 跟进 [flink-agents 官方框架](https://github.com/apache/flink-agents)（2025 年发布）

---

## 数据源演进全视图

| 阶段 | 数据源 | 说明 |
|------|--------|------|
| Week 1–2 | `datagen`（内置） | 零依赖，专注验证 Agent 链路 |
| Phase 2 | `datagen → Kafka → Flink` | 用 Flink SQL 作业往 Kafka 写数据再消费，不需要额外 producer 程序 |
| Phase 3+ | 真实业务数据 | 接入实际 Kafka topic |
