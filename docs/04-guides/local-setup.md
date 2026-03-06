# 本地环境启动指南

> 上次更新：2026-03-05
> 适用人群：第一次启动或排查基础设施问题

---

## 前置条件

| 工具 | 最低版本 | 检查命令 |
|------|---------|---------|
| Docker | 24.x | `docker --version` |
| Docker Compose | v2.x（`docker compose` 命令，非旧版 `docker-compose`） | `docker compose version` |
| uv | 0.5+ | `uv --version` |
| 可用内存 | 4 GB（最低 2 GB） | `free -h` |

---

## 步骤 1：准备 Flink 配置文件

```bash
mkdir -p ./flink-conf
```

创建 `flink-conf/config.yaml`（Flink 2.x 使用 YAML 嵌套格式，旧式扁平格式已废弃）：

```yaml
# flink-conf/config.yaml
jobmanager:
  rpc:
    address: flink-jobmanager    # 必须与 docker-compose.yml 中的服务名一致
  memory:
    process:
      size: 1600m

taskmanager:
  memory:
    process:
      size: 1728m                # 内存不足时可调低到 1024m

sql-gateway:
  endpoint:
    rest:
      address: 0.0.0.0
      port: 8083
```

> 💡 更多配置选项见 [`flink-config.md`](./flink-config.md)

---

## 步骤 2：准备 Connector JARs（Week 1 可跳过）

Week 1 只用 `datagen` connector，Flink 镜像自带，**不需要下载任何 JAR**。

创建空目录即可（docker-compose.yml 中挂载该目录）：

```bash
mkdir -p ./flink-lib
```

Week 2+ 需要连接 PostgreSQL 时，再按 [`connector-jars.md`](./connector-jars.md) 下载。

---

## 步骤 3：配置环境变量

复制示例文件并填入你的 LLM API Key：

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
# LLM 配置（OpenRouter 或兼容 OpenAI 格式的 API）
LLM_API_KEY=sk-or-xxxx
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-chat

# PostgreSQL（与 docker-compose.yml 中的设置对应）
POSTGRES_PASSWORD=secret
DATABASE_URL=postgresql://postgres:secret@localhost:5432/flinkpilot

# Flink 服务地址（从 backend 容器访问）
FLINK_REST_URL=http://flink-jobmanager:8081
FLINK_SQL_GATEWAY_URL=http://flink-sql-gateway:8083
```

---

## 步骤 4：启动所有服务

```bash
docker compose up -d
```

第一次启动会拉取镜像（Flink 2.2 约 800 MB），需要等待。

### 验证所有服务健康

```bash
docker compose ps
```

期望看到所有服务状态为 `healthy` 或 `running`：

```
NAME                      STATUS
flink-jobmanager          Up (healthy)
flink-taskmanager         Up
flink-sql-gateway         Up (healthy)
flinkpilot-db             Up (healthy)
```

### 验证各服务可访问

```bash
# Flink Web UI（浏览器打开）
open http://localhost:8081

# SQL Gateway REST API
curl http://localhost:8083/v1/info

# PostgreSQL
docker compose exec db psql -U postgres -d flinkpilot -c "SELECT 1;"
```

---

## 步骤 5：启动后端（开发模式）

```bash
cd backend
uv sync

# 热重载模式启动
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 步骤 6：启动前端（Gradio，Phase 1）

```bash
cd backend
uv run python gradio_app.py   # Phase 1 MVP 前端
```

打开 `http://localhost:7860` 即可使用。

---

## 常用操作

```bash
# 查看所有容器日志
docker compose logs -f

# 只看 JobManager 日志
docker compose logs -f flink-jobmanager

# 只看 SQL Gateway 日志
docker compose logs -f flink-sql-gateway

# 停止所有服务（保留数据）
docker compose down

# 停止并清除所有数据（重置环境）
docker compose down -v
```

---

## 常见问题排查

### Q: SQL Gateway 一直 unhealthy

**可能原因**：JobManager 还没完全启动，Gateway 连不上。

```bash
# 观察 Gateway 日志
docker compose logs flink-sql-gateway

# 通常等待 30-60 秒会自动恢复
# 或手动重启 Gateway
docker compose restart flink-sql-gateway
```

### Q: `ClassNotFoundException` 提交 SQL 时报错

**原因**：`flink-lib/` 目录里有旧版 connector JAR（`-1.19` 或 `-1.20` 后缀）。

```bash
ls ./flink-lib/
# 删除旧 JAR，按 connector-jars.md 重新下载
```

### Q: PostgreSQL 连接失败

```bash
# 检查容器是否健康
docker compose ps db

# 检查密码是否与 .env 中的 POSTGRES_PASSWORD 一致
docker compose exec db psql -U postgres -d flinkpilot
```

### Q: `FLINK_PROPERTIES` 警告

如果日志里出现关于 `FLINK_PROPERTIES` 的弃用警告，说明有地方仍在用旧的环境变量注入方式。正确做法是挂载 `config.yaml` 文件。本项目已通过 `volumes: - ./flink-conf:/opt/flink/conf` 挂载。

### Q: 内存不足，容器 OOM

修改 `flink-conf/config.yaml`：

```yaml
taskmanager:
  memory:
    process:
      size: 1024m    # 从 1728m 降低到 1024m
```

重启：`docker compose restart flink-taskmanager`
