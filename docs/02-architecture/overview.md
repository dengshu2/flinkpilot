# 整体架构概览

> 迁移自 flinkpilot_architecture.md § 二、整体架构
> 上次更新：2026-03-05

---

## 三层架构图

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

## 各层职责

### 用户界面层

- **MVP**：Gradio，1 天搭建，快速验证核心链路
- **产品化**：Vue 3 + Vite，支持 WebSocket 流式输出
- **DAG 可视化**：AntV X6（只读渲染，Agent 输出 JSON，前端负责展示，不需要拖拉拽）

### Agent 核心层

- **FastAPI**：异步 HTTP + WebSocket 服务，作为 Agent 的接入层
- **LangGraph 1.0**：多步骤 ReAct 循环，含 Durable State（PostgreSQL 持久化）
- **Tool 路由**：按意图分发到不同 Skill（SQL 生成、JAR 构建、监控诊断）

详细设计见 [agent-design.md](./agent-design.md)。

### 基础设施层

| 组件 | 版本 | 职责 |
|------|------|------|
| Flink JobManager | 2.2 | 作业调度和协调 |
| Flink TaskManager | 2.2 | 实际执行算子计算 |
| Flink SQL Gateway | 2.2 | 接收 SQL 语句，Session mode 提交作业 |
| PostgreSQL | 15 | 业务数据库 + LangGraph 状态持久化（一库两用） |
| Nginx | alpine | 反向代理，统一入口 |

---

## 前端选型说明

| 阶段 | 方案 | 工作量 | 理由 |
|------|------|--------|------|
| MVP 验证期 | **Gradio** | 1 天 | 快速跑通核心链路，不需要写前端代码 |
| 产品化 | **Vue 3 + Vite** | 3–5 天 | 轻量，WebSocket 友好，中文生态好 |
| 用户规模增长后 | Next.js（待定） | — | 有 SEO 需求时再迁移 |

---

## 内存估算（单 VPS 部署）

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
