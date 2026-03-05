# ADR-003: SQL Gateway Session Mode vs Application Mode 取舍

- **状态**：已接受（分阶段策略）
- **日期**：2026-03-05
- **决策者**：项目负责人

## 背景

Flink SQL Gateway 支持两种提交模式，选择哪种直接影响资源隔离性和开发复杂度。MVP 阶段和产品化阶段对可用性的要求不同，需要明确分阶段策略。

## 两种模式对比

| 维度 | Session Mode | Application Mode |
|------|-------------|-----------------|
| 资源隔离 | ❌ 所有作业共享 TaskManager | ✅ 每个作业独立 TaskManager |
| 一个作业 OOM 的影响 | 影响同 Session 内所有作业 | 只影响该作业本身 |
| 启动速度 | 快（复用已有 Session） | 慢（每次起新集群） |
| SQL Gateway 原生支持 | ✅ 完整支持 | ⚠️ Flink 2.x 中尚不完整（FLIP-316 仍在推进） |
| 实现复杂度 | 低 | 高（需 Kyuubi 或 JAR 封装） |

## 决策：分阶段策略

### MVP 阶段（Phase 1-2）：Session Mode

理由：
- 我们只有 1 个 VPS，同时运行的作业数量极少（通常 1-3 个）
- Session mode 的资源竞争问题在低并发下几乎不显现
- 开发速度优先，Session mode 跳过 JAR 打包，最快路径

### 产品化阶段（Phase 3+）：Kyuubi + Application Mode

理由：
- 随着用户增多，不同用户的作业需要资源隔离
- 直接使用 SQL Gateway 的 Application mode 原生支持尚不完整
- **推荐方案：Apache Kyuubi**，开源项目，原生支持 Flink Application Mode + 多租户

备选方案（不推荐）：将 SQL 封装成 JAR 后通过 REST API 提交（复杂度高，放弃 SQL Gateway 优势）。

## 后果

- **正面**：MVP 阶段开发速度快，产品化阶段有明确路径
- **风险**：忘记切换，在产品化阶段仍用 Session mode 导致稳定性问题
- **跟进**：Phase 3 开始前评估 FLIP-316 的完成情况，如官方已完整支持，可不引入 Kyuubi

## 参考

- [FLIP-316: SQL Gateway Application Mode 原生支持](https://cwiki.apache.org/confluence/display/FLINK/)
- [Apache Kyuubi 文档](https://kyuubi.apache.org)
