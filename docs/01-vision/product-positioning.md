# FlinkPilot 产品定位

> 迁移自 flinkpilot_architecture.md § 一、产品定位
> 上次更新：2026-03-05

---

## 核心定位

**不是"Flink 的遥控器"，而是"Flink 的副驾驶"**

```
用户说：帮我从 Kafka 读用户点击数据，按 5 分钟窗口统计 PV，写入 PostgreSQL
Agent：  理解意图 → 生成 SQL → 验证 → 提交 → 监控 → 异常诊断
```

| 维度 | 传统拖拉拽平台 | FlinkPilot |
|------|--------------|-----------|
| 输入方式 | 手动拖拽节点、填参数 | 自然语言描述意图 |
| 可视化 | 输入层（用户操作） | 结果层（AI 生成后展示） |
| 作业监控 | 被动查看 | Agent 主动推送 + 诊断建议 |
| 定位 | 2018–2022 范式 | 2025–2026 范式 |

---

## 竞品对比与差异化

| 竞品/方向 | 定位 | 与 FlinkPilot 的差异 |
|----------|------|---------------------|
| **官方 flink-agents** | Apache 官方子项目，Python/Java API，事件驱动 | 偏底层框架，无开箱即用 UI；FlinkPilot 是其上层产品 |
| **Confluent + MCP** | 通过 MCP 让 LLM 直接与 Kafka/Flink 交互 | 企业级，重 Kafka 生态，FlinkPilot 轻量化单 VPS |
| **Databricks Genie** | 自然语言编写 Spark/Delta 管道 | Databricks 生态锁定，云端 SaaS |
| **GenFuse AI** | 无代码 AI Pipeline 构建器 | 通用 AI 工作流，不理解 Flink 语义 |

### 核心护城河

FlinkPilot 的差异化不在于"自然语言 + Flink"（这个方向已有多家在做），而在于：

1. **深度 Flink 语义理解**：理解 watermark、backpressure、checkpoint 等专有概念，不是泛化 SQL 生成
2. **全流程 Agent 闭环**：生成 → 验证 → 提交 → 监控 → 诊断 → 修复，形成完整循环
3. **单 VPS 可部署**：个人开发者和小团队无需云厂商锁定
4. **与官方 flink-agents 互补**：将 flink-agents 作为工具层，FlinkPilot 作为产品层

---

## 成本估算

| 项目 | 费用 |
|------|------|
| VPS（4C8G，Hetzner / 腾讯云轻量） | ¥50–200/月 |
| LLM API（日常开发 + 压测） | ¥50–200/月 |
| 域名 + SSL | ¥50–100/年 |
| **合计** | **约 ¥100–400/月** |

> 使用国内模型（DeepSeek、通义千问）可将 LLM API 成本降低 70–90%，且延迟更低，建议作为首选。

---

## 待定决策

- **商业模式**：To-C 订阅 / To-B 私有化 / 开源项目——需在 Phase 2 结束前确认，影响 Phase 3 UI 设计优先级
