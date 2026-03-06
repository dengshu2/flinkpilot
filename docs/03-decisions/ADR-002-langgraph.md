# ADR-002: 选用 LangGraph 1.0 作为 Agent 框架

- **状态**：已接受
- **日期**：2026-03-05
- **决策者**：项目负责人

## 背景

FlinkPilot 的核心是一个多步骤 Agent：理解意图 → 生成 SQL → 验证 → 提交 → 监控 → 诊断。需要一个能处理有状态、长流程、可中断 Agent 的框架。

## 考虑的选项

| 选项 | 优点 | 缺点 |
|------|------|------|
| **LangGraph 1.0** | Durable State（PostgreSQL 持久化）、Human-in-the-loop 原生支持、Python 生态成熟 | 学习曲线中等，API 在 1.0 前变化较频繁 |
| **CrewAI** | 角色分工直观，适合多 Agent 协作 | 无原生 Durable Execution，长流程断点续跑需自己实现 |
| **AutoGen** | 微软背书，多 Agent 对话场景强 | 对单 Agent 多工具的场景偏重，状态管理不如 LangGraph |
| **自行实现 ReAct 循环** | 灵活，无框架依赖 | 需要自行实现持久化、human-in-the-loop、流式输出，工作量大 |

## 决策

选择 **LangGraph 1.0**（2025 年 10 月正式发布）。

核心理由：
1. **Durable Execution**：Agent 状态自动持久化到 PostgreSQL，VPS 重启后长流程（如生成 → 打包 → 部署）可从断点续跑，无需自己维护 checkpoint 逻辑
2. **Human-in-the-loop**：kill job 等高风险操作前暂停等待用户确认，框架原生支持
3. **PostgresSaver 一库两用**：PostgreSQL 同时作为业务数据库和 LangGraph checkpointer，减少基础设施复杂度
4. **Flink 场景匹配**：Flink 作业的生命周期（提交 → 运行 → 监控 → 异常 → 诊断）天然是有状态的多步 ReAct 循环

## 依赖注意事项

```toml
# pyproject.toml 中的核心依赖（uv 管理）
[project]
dependencies = [
    "langgraph>=1.0.0",
    "langchain-openai>=0.3.0",
    "psycopg[binary]>=3.1.0",   # psycopg3，不是 psycopg2-binary
]
```

LangGraph 1.0 的 `PostgresSaver` 依赖 psycopg3（`psycopg`），而不是旧的 psycopg2。在 Docker 镜像中需确认使用正确版本。

## 后果

- **正面**：会话历史天然存储，省去大量 DB 模板代码
- **负面**：LangGraph 的 graph 概念需要一定学习成本
- **跟进**：关注官方 flink-agents 项目，未来可将其作为工具层集成进来
