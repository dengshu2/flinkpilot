# ADR-001: 选用 Flink 2.2 而非 Flink 1.x

- **状态**：已接受
- **日期**：2026-03-05
- **决策者**：项目负责人

## 背景

项目需要一个稳定、具备 AI 集成能力的 Flink 版本用于 SQL 作业生成与提交。当前生产环境中大量项目仍使用 Flink 1.18，是否应该跟进最新版本需要明确决策。

## 考虑的选项

| 选项 | 优点 | 缺点 |
|------|------|------|
| **Flink 1.18**（旧稳定版） | 社区资源丰富，网上案例多 | Java 8 兼容性包袱重，无 ML_PREDICT，Materialized Tables 不可用 |
| **Flink 2.2**（当前最新稳定版） | Java 11+，ML_PREDICT，Materialized Tables 生产就绪，Disaggregated State | Connector JAR 需升级，LLM 训练数据以 1.x 为主 |

## 决策

选择 **Flink 2.2**（截至 2026-03 的最新稳定版）。

核心理由：
1. **ML_PREDICT**：Flink SQL 内原生调用 LLM，是 Phase 4 的核心差异化功能
2. **Materialized Tables**：流批统一声明式管道，直接可用，降低用户学习成本
3. **Disaggregated State**：状态分离 DFS，为将来大状态作业铺路
4. **Per-job 模式已移除**：迫使我们从一开始就用 Application mode 思维设计，避免后期迁移

## 需要注意的风险

- **Connector JAR 版本**：必须使用面向 Flink 2.x 的兼容版本（`-2.x` 后缀），旧版 `-1.19`/`-1.20` JAR 在 2.x 会报 `ClassNotFoundException`
- **LLM 生成代码的 API 兼容性**：LLM 训练数据以 Flink 1.x 代码为主，Phase 2 JAR 构建时需在 Prompt 中明确指定 DataStream API V2
- **config.yaml 格式**：旧 `flink-conf.yaml` 已废弃，需提供 `flink-conf/config.yaml`

## 跟进项

- [ ] 每次 Flink 小版本升级时评估 Connector JAR 是否需要同步更新
- [ ] Phase 4 开始时评估 ML_PREDICT 的成熟度和可用性
