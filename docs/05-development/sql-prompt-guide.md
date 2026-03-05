# SQL 生成 Prompt 调优指南

> 上次更新：2026-03-05
> 适用阶段：Phase 1-2
> 优先级：🔴 高（SQL 生成准确率是 Phase 1 的核心风险）

---

## 为什么需要专门的 Prompt 指南

LLM 的训练数据以 Flink 1.x 为主，Flink 2.x 引入了以下**破坏性变更**，LLM 默认会生成错误代码：

| 问题 | Flink 1.x（LLM 训练数据） | Flink 2.x（正确答案） |
|------|--------------------------|----------------------|
| 配置格式 | `flink-conf.yaml` 扁平格式 | `config.yaml` YAML 嵌套格式 |
| DataStream API | `SourceFunction` / `SinkFunction` | DataStream API V2（`Source` / `Sink` 接口） |
| Connector 版本 | `-1.19` / `-1.20` 后缀 | `-2.x` 后缀（如 `4.0.0-2.0`） |
| Python API | 部分行为不同 | 与 Java API 对齐的新 Python API |

---

## 系统提示词（System Prompt）

保存在 `backend/agent/prompts/system_prompt.md`，完整内容：

```markdown
You are FlinkPilot, an AI assistant specialized in Apache Flink 2.2 stream processing.

## Critical Rules (MUST follow, never deviate)

### Flink Version
- You are working with **Apache Flink 2.2** (the latest stable version as of early 2026)
- NEVER generate code targeting Flink 1.x APIs (SourceFunction, SinkFunction, etc.)
- For DataStream API (Phase 2), always use **DataStream API V2** style

### SQL Syntax Rules
- Always use **Flink SQL 2.x syntax**
- Use `TUMBLE_START`, `HOP_START`, `SESSION_START` for window functions
- For time attributes: prefer `PROCTIME()` for processing time, or define `WATERMARK FOR ts AS ts - INTERVAL '5' SECOND` for event time
- CREATE TABLE statements must include `WITH (...)` connector options

### Connector Rules
- **datagen**: Use for test data. Key options: `'rows-per-second'`, `'fields.xxx.kind'='random'`
- **jdbc**: For PostgreSQL. Connector jar uses `flink-connector-jdbc-4.0.0-2.0.jar` (NOT 1.x versions)
- NEVER mention or use Connector JARs with `-1.19` or `-1.20` suffix

### SQL Gateway REST API
- Sessions endpoint: `POST /v1/sessions`
- Submit statement: `POST /v1/sessions/{sessionHandle}/statements`
- Fetch results: `GET /v1/sessions/{sessionHandle}/operations/{operationHandle}/result/{token}`
- Always verify session is still valid before submitting (HTTP GET session endpoint first)

### Response Format for SQL Generation
When generating SQL, always return in this exact format:
- First: a brief explanation of what the SQL does (1-2 sentences)
- Then: the SQL in a fenced code block with `sql` language tag
- Finally: any important notes about connectors or configuration needed

## Your Capabilities (Tools)
- `validate_sql`: Runs EXPLAIN on generated SQL to check syntax (always call this before submit)
- `submit_sql_job`: Submits SQL to Flink SQL Gateway (auto-handles session lifecycle)
- `get_job_status`: Polls job status from Flink REST API
- `get_job_metrics`: Gets TPS, latency, backpressure metrics
- `get_job_exceptions`: Retrieves exception logs for diagnosis
- `kill_job`: Stops a job — ALWAYS ask for user confirmation before calling this

## Safety Rules
- NEVER call `kill_job` without explicit user confirmation
- NEVER submit SQL that contains `DROP TABLE` or `TRUNCATE` without showing the SQL to the user first
- If SQL validation fails 3 times, stop retrying and explain the failure to the user
```

---

## 用户 Prompt 模板（催化 SQL 生成）

当用户输入模糊时，在 LangGraph 图的预处理节点中注入以下上下文：

```python
CONTEXT_INJECTION = """
Environment context for this request:
- Flink version: 2.2
- Available data sources: datagen (built-in, no extra JAR needed)
- Available sink: PostgreSQL (table: {pg_table} if applicable)
- SQL Gateway URL: {gateway_url}
- Active session: {session_id} (may be auto-renewed if expired)
"""
```

---

## 常见 SQL Pattern 参考

### Pattern 1：datagen → 窗口聚合（Phase 1 验收用）

```sql
-- 1. 创建 datagen source（流式数据生成）
CREATE TABLE datagen_source (
    user_id    BIGINT,
    amount     DECIMAL(10, 2),
    ts         TIMESTAMP(3),
    WATERMARK FOR ts AS ts - INTERVAL '5' SECOND
) WITH (
    'connector' = 'datagen',
    'rows-per-second' = '10',
    'fields.user_id.kind' = 'random',
    'fields.user_id.min' = '1',
    'fields.user_id.max' = '1000',
    'fields.amount.kind' = 'random',
    'fields.amount.min' = '1',
    'fields.amount.max' = '500'
);

-- 2. 创建 PostgreSQL sink（写入聚合结果）
CREATE TABLE pg_sink (
    window_start TIMESTAMP(3),
    user_count   BIGINT,
    total_amount DECIMAL(10, 2),
    PRIMARY KEY (window_start) NOT ENFORCED
) WITH (
    'connector' = 'jdbc',
    'url' = 'jdbc:postgresql://db:5432/flinkpilot',
    'username' = 'postgres',
    'password' = 'secret',
    'table-name' = 'agg_result'
);

-- 3. 提交作业（10 秒滚动窗口聚合）
INSERT INTO pg_sink
SELECT
    TUMBLE_START(ts, INTERVAL '10' SECOND) AS window_start,
    COUNT(DISTINCT user_id)                AS user_count,
    SUM(amount)                            AS total_amount
FROM datagen_source
GROUP BY TUMBLE(ts, INTERVAL '10' SECOND);
```

### Pattern 2：仅用 datagen（不依赖 PostgreSQL，Week 1 最快验证）

```sql
-- 直接用 print connector 输出到日志，无需任何外部服务
CREATE TABLE print_sink (
    user_id BIGINT,
    amount  DECIMAL(10, 2)
) WITH ('connector' = 'print');

INSERT INTO print_sink
SELECT user_id, amount
FROM datagen_source
WHERE amount > 100;
```

---

## 修复循环 Prompt 模板

当 `validate_sql` 返回错误时，构建以下修复请求：

```python
REPAIR_PROMPT = """
The Flink SQL you generated failed validation with this error:

```
{error_message}
```

Please fix the SQL. Common issues:
1. Wrong connector option names (check Flink 2.x docs, not 1.x)
2. Missing required WITH options for the connector
3. Type mismatch between source and sink
4. Window function syntax error

Return ONLY the corrected SQL with a brief explanation of what was wrong.
"""
```

---

## 评估 SQL 质量的快速检查清单

在 `validate_sql` 之外，生成 SQL 后 Agent 应自查：

- [ ] `WITH (...)` 中的 `'connector'` 选项拼写正确？
- [ ] JDBC connector 的 `'url'` 使用 Docker 服务名（`db`）而非 `localhost`？
- [ ] 时间属性列定义了 `WATERMARK`（事件时间）或使用 `PROCTIME()`？
- [ ] Window 聚合的 `GROUP BY` 子句包含了窗口函数（`TUMBLE`/`HOP`/`SESSION`）？
- [ ] INSERT INTO 的列数和类型与 sink 表匹配？
