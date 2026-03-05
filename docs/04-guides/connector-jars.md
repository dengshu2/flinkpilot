# Connector JARs 准备指南

> 适用版本：Flink 2.2
> 上次更新：2026-03-05

官方 Flink Docker 镜像**不包含** Kafka / JDBC 等 connector，必须在启动前手动下载并挂载到 `./flink-lib/` 目录。

---

## 重要：版本必须匹配 Flink 2.x

> ⚠️ Flink 2.0 移除了旧的 `SourceFunction` / `SinkFunction` 接口。使用后缀为 `-1.19`、`-1.20` 的旧版 JAR 会在运行时报 `ClassNotFoundException`，且错误信息不直观，极难排查。

JAR 文件名规则：
- ✅ 正确：`flink-sql-connector-kafka-4.0.0-2.0.jar`（`-2.0` 表示面向 Flink 2.x）
- ❌ 错误：`flink-sql-connector-kafka-3.3.0-1.20.jar`（`-1.20` 表示面向 Flink 1.20）

---

## 下载命令

```bash
mkdir -p ./flink-lib

# Kafka connector（面向 Flink 2.x 的兼容版）
wget -P ./flink-lib \
  https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/4.0.0-2.0/flink-sql-connector-kafka-4.0.0-2.0.jar

# JDBC connector（面向 Flink 2.x）
wget -P ./flink-lib \
  https://repo.maven.apache.org/maven2/org/apache/flink/flink-connector-jdbc/4.0.0-2.0/flink-connector-jdbc-4.0.0-2.0.jar

# PostgreSQL JDBC 驱动（版本无关 Flink，保持最新即可）
wget -P ./flink-lib \
  https://jdbc.postgresql.org/download/postgresql-42.7.3.jar
```

---

## 如果版本号有变化

在以下地址手动搜索最新的 2.x 兼容版本：

```
https://repo.maven.apache.org/maven2/org/apache/flink/
```

搜索关键词：`flink-sql-connector-kafka`，选择目录中版本号包含 `-2.x` 的最新版。

---

## 验证下载结果

```bash
ls -lh ./flink-lib/
# 期望看到：
# flink-sql-connector-kafka-4.0.0-2.0.jar   (~12 MB)
# flink-connector-jdbc-4.0.0-2.0.jar         (~4 MB)
# postgresql-42.7.3.jar                       (~1 MB)
```

---

## Phase 1（Week 1-2）可以跳过

如果你只用 `datagen` connector 跑端到端验证（Week 1 的推荐方式），**不需要下载任何 JAR**。`datagen` 是 Flink 内置 connector，所有镜像均自带。

只有当你需要连接 Kafka 或写入 PostgreSQL 时，才需要这些 JAR。
