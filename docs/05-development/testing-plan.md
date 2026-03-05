# FlinkPilot Phase 1 测试方案

> 创建时间：2026-03-06
> 状态：📋 **待评估执行**（Phase 1 代码完成后的测试补充项）
> 负责人：下一个 AI Session 或人工 QA

---

## 背景与动机

Phase 1 的端到端冒烟测试（手动）已通过，但缺乏：
1. **可重复执行的自动化测试用例**
2. **边界条件和错误路径覆盖**
3. **性能基线数据**

这份文档定义 Phase 1 的完整测试方案，确保在进入 Phase 2 开发前有足够的质量保证基线。

---

## 测试层次

```
Unit Tests       → 单个 Tool 函数的逻辑
Integration Tests → Tool + Flink Gateway 的真实交互
E2E Tests        → 完整 Agent 链路（NL → SQL → Submit → Job Running）
Regression Tests → 每次代码变更后自动跑
```

---

## 一、Unit Tests（无需 Flink 运行）

### 1.1 `_split_sql_statements` 函数

| 测试用例 | 输入 | 期望输出 |
|----------|------|----------|
| 单条语句 | `"SELECT 1"` | `["SELECT 1"]` |
| 多条语句 | `"CREATE TABLE t1 (...); INSERT INTO t1 SELECT ..."` | `["CREATE TABLE t1 (...)", "INSERT INTO t1 SELECT ..."]` |
| 尾部分号 | `"SELECT 1;"` | `["SELECT 1"]` |
| 空注释行 | `"-- comment\nSELECT 1"` | `["SELECT 1"]` |
| 仅空白 | `"  ;  ;  "` | `[]` |

### 1.2 `_extract_readable_error` 函数

| 测试用例 | 输入（errors 列表） | 期望输出（包含） |
|----------|---------------------|-----------------|
| ValidationException | `["Internal...", "...Caused by: ValidationException: Object 'foo' not found..."]` | `"Object 'foo' not found"` |
| 纯内部错误 | `["Internal server error."]` | `"未知错误"` 或非空字符串 |
| 空列表 | `[]` | `"未知错误"` |

### 1.3 `get_job_status` job_id 清理

| 输入 | 期望调用的 URL |
|------|---------------|
| `"abc123"` | `/jobs/abc123` |
| `"a1b2-c3d4-e5f6-g7h8-i9j0k1l2m3n4"` | `/jobs/a1b2c3d4e5f6g7h8i9j0k1l2m3n4"` |

**生成测试文件：** `backend/tests/test_flink_tools_unit.py`

```python
# 示例结构
import pytest
from agent.tools.flink_tools import _split_sql_statements, _extract_readable_error

def test_split_single_statement():
    assert _split_sql_statements("SELECT 1") == ["SELECT 1"]

def test_split_multi_statements():
    sql = "CREATE TABLE t (id INT) WITH ('connector'='datagen'); INSERT INTO t SELECT * FROM s"
    parts = _split_sql_statements(sql)
    assert len(parts) == 2
    assert parts[0].startswith("CREATE TABLE")
    assert parts[1].startswith("INSERT INTO")

def test_split_ignores_empty():
    assert _split_sql_statements("  ;  ;  ") == []

def test_extract_error_validation_exception():
    errors = [
        "Internal server error.",
        "<Exception...\\nCaused by: ValidationException: Object 'bad_table' not found\\n..."
    ]
    result = _extract_readable_error(errors)
    assert "bad_table" in result or "not found" in result.lower()
```

---

## 二、Integration Tests（需要 Flink Gateway 运行）

### 2.1 `validate_sql` — 正常路径

```
场景：有效的 multi-statement SQL（DDL + INSERT INTO）
输入：
  sql = """
    CREATE TEMPORARY TABLE src (id INT, proc_time AS PROCTIME())
    WITH ('connector'='datagen');

    CREATE TEMPORARY TABLE snk (cnt BIGINT)
    WITH ('connector'='print');

    INSERT INTO snk SELECT COUNT(*) FROM src
    GROUP BY TUMBLE(proc_time, INTERVAL '5' SECOND)
  """
期望：
  valid=True, error="", session_id 非空
```

### 2.2 `validate_sql` — 错误路径

| 测试场景 | SQL | 期望 |
|----------|-----|------|
| 引用不存在的表 | `"INSERT INTO nonexistent SELECT 1"` | `valid=False`，error 包含表名 |
| 类型不匹配 | `... BIGINT 字段 INSERT STRING 值 ...` | `valid=False`，error 非空 |
| 空 SQL | `""` | `valid=False`，error 包含"未解析" |
| 语法错误 | `"SELEKT * FROM t"` | `valid=False` |

### 2.3 `submit_sql_job` — 正常路径

```
场景：提交合法的流式作业
输入：同 2.1 的 SQL
期望：
  status="SUBMITTED"
  operation_handle 非空
  job_id 非空（32 位 hex）
  job_id 在 /jobs/overview 中能查到且 state=RUNNING
```

### 2.4 `submit_sql_job` — 错误路径

| 测试场景 | 期望 |
|----------|------|
| DDL 失败（无效 connector） | `status="ERROR"`，error 包含原因 |
| Session 失效后自动重建 | 手动让 session 过期，再次调用仍成功 |

---

## 三、E2E Tests（完整 Agent 链路）

### 3.1 Happy Path — 标准 datagen + print 作业

```
用户输入：
  "用 datagen 每秒生成 5 条数据（id INT, score DOUBLE），
   每 10 秒处理时间窗口统计平均分，用 print connector 打印"

期望 Agent 行为：
  1. 自动调用 validate_sql（不调用 generate_flink_sql tool）
  2. validate 通过
  3. 自动调用 submit_sql_job
  4. 返回 job_id（32 位 hex）
  5. 在 /jobs/overview 中 job_id 存在且 state=RUNNING

性能基线：
  全程耗时 < 60 秒（不含第一次 LLM 冷启动）
```

### 3.2 SQL 修复路径（重试循环）

```
用户输入（故意包含错误）：
  "用 datagen 生成数据，用 fields.action.values 指定 click/view/buy（会触发 datagen 不支持该参数的错误），
   每 10 秒统计各 action 次数"

期望 Agent 行为：
  1. 生成 SQL（包含 datagen 不支持的 fields.xxx.values 选项）
  2. validate 失败，error 被注入回 Agent
  3. Agent 重新生成 SQL（用 CASE 表达式替代）
  4. 第二次 validate 通过
  5. 成功提交

验证点：
  - sql_retry_count 在 error state 中递增
  - 最终回复中没有 fields.xxx.values 语法
```

### 3.3 超时和边界

| 场景 | 输入 | 期望 |
|------|------|------|
| 超长描述 | 500 字以上的需求描述 | 正常处理，不崩溃 |
| 要求不支持的功能 | "用 Kafka source（未安装 JAR）" | validate 失败，给出清晰提示 |
| 用户明确说不提交 | "只生成 SQL，不要提交" | Agent 只返回 SQL 不调用 submit_sql_job |

---

## 四、回归测试套件（CI 建议）

建议在 GitHub Actions / CI 中配置：

```yaml
# .github/workflows/phase1-regression.yml（待创建）
jobs:
  unit-tests:
    # 不需要 Docker，只跑 pytest backend/tests/test_*.py -k "unit"

  integration-tests:
    services:
      flink-gateway: ...  # 用 docker-compose 启动
    # 跑 pytest backend/tests/test_*.py -k "integration" --timeout=60
```

---

## 五、已知问题 / 待研究（与测试相关）

### 🔴 P1：print connector 输出在 Flink Web UI 不可见

**问题描述：**
Flink Web UI → Task Managers → Stdout 显示 *"The file STDOUT does not exist on the TaskExecutor"*。
实际数据确实在流出（可通过 `docker logs flink-taskmanager -f` 验证），但 Web UI 看不到。

**影响：**
- Phase 1 测试只能通过 docker logs 验证输出，用户体验差
- E2E 测试自动化困难（难以断言 print 输出内容）

**建议研究方向（优先级由高到低）：**
1. **Flink 配置方向**：查看 `env.log.dir`、`taskmanager.log.path` 是否可以将 stdout 写入文件；参考官方文档 [Flink Configuration Options](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/deployment/config/)
2. **搜索关键词**：`"Flink Docker standalone mode print connector stdout web ui"` / `"taskmanager stdout file does not exist docker"`
3. **替代 sink 方案**：将 print 换成 PostgreSQL sink（`flink-connector-jdbc`），结果写入 `test_output` 表，测试时 `SELECT * FROM test_output` 做断言——这也是 Phase 1 → Phase 2 更真实的验收场景

### 🟡 P2：`get_job_id` 竞争条件

多作业并发时，`submit_sql_job` 轮询最新 RUNNING 作业可能拿错 job_id。
**研究方向**：SQL Gateway `/result/0` 接口返回值是否包含 `jobId` 字段（Flink 2.2 版本）。

---

## 六、测试执行优先级建议

| 优先级 | 任务 | 预估工时 |
|--------|------|----------|
| 🔴 P0 | 研究并修复 print stdout 可见性问题 | 2-4h |
| 🔴 P0 | 用 PostgreSQL sink 替代 print 做完整 E2E 验证 | 3h |
| 🟠 P1 | 编写 `test_flink_tools_unit.py`（Unit Tests） | 2h |
| 🟠 P1 | 编写 `test_integration.py`（Integration Tests） | 4h |
| 🟡 P2 | 研究 job_id 竞争条件，修复或文档说明 | 1-2h |
| 🟢 P3 | 配置 CI/CD 自动化回归测试 | Phase 2 后期 |
