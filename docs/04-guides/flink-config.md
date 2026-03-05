# Flink config.yaml 配置参考

> 适用版本：Flink 2.x（2.0 起 `flink-conf.yaml` 已废弃，改用严格 YAML 格式的 `config.yaml`）
> 上次更新：2026-03-05

---

## 创建配置文件

在项目根目录创建 `flink-conf/config.yaml`（Docker Compose 会将其挂载到所有 Flink 容器）：

```bash
mkdir -p ./flink-conf
```

---

## 配置文件内容

```yaml
# flink-conf/config.yaml
# Flink 2.x 使用严格标准 YAML 格式，不再支持旧式 key: value 扁平写法

jobmanager:
  rpc:
    address: flink-jobmanager    # 必须与 docker-compose 中的服务名一致
  memory:
    process:
      size: 1600m                # JobManager 进程内存，含 JVM overhead

taskmanager:
  memory:
    process:
      size: 1728m                # TaskManager 进程内存
      # VPS 内存不足时可调低到 1024m，但低于 768m 会导致 OOM

sql-gateway:
  endpoint:
    rest:
      address: 0.0.0.0           # 允许容器外访问，Docker 网络内通信需要
      port: 8083
```

---

## 内存参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `jobmanager.memory.process.size` | 1600m | JobManager 进程总内存 |
| `taskmanager.memory.process.size` | 1728m | TaskManager 进程总内存 |

**4G VPS** 完全够用；**2G VPS** 可将 TaskManager 调低到 `1024m`，JobManager 调低到 `1024m`。

---

## 旧格式 vs 新格式对比

```
# ❌ 旧格式（Flink 1.x，flink-conf.yaml）
jobmanager.rpc.address: flink-jobmanager
taskmanager.memory.process.size: 1728m

# ✅ 新格式（Flink 2.x，config.yaml）
jobmanager:
  rpc:
    address: flink-jobmanager
taskmanager:
  memory:
    process:
      size: 1728m
```

---

## 如何验证配置生效

启动后进入 JobManager 容器检查：

```bash
docker compose exec flink-jobmanager cat /opt/flink/conf/config.yaml
```

---

## ⚠️ Docker Compose 挂载陷阱（必读）

### 陷阱 1：目录挂载会覆盖 /opt/flink/conf/ 内所有文件

`/opt/flink/conf/` 镜像内有 11 个文件（log4j.properties、masters、workers 等），如果用目录挂载：

```yaml
# ❌ 错误！空的 ./flink-conf/ 目录会覆盖 conf/ 内所有文件
volumes:
  - ./flink-conf:/opt/flink/conf
```

Flink 将因找不到 log4j 等配置而崩溃，报 `Flink distribution jar not found` 的误导性错误。

**正确做法：只挂载单个文件：**

```yaml
# ✅ 正确：只覆盖 config.yaml，其余文件保留镜像默认
volumes:
  - ./flink-conf/config.yaml:/opt/flink/conf/config.yaml
```

### 陷阱 2：flink-lib 空目录不能挂载到 /opt/flink/lib

`/opt/flink/lib/` 镜像内含 `flink-dist-2.2.0.jar` 等核心 JAR。挂载空的 `./flink-lib/` 会覆盖它们，导致相同的崩溃错误。

- **Week 1（datagen）**：不需要任何挂载，镜像自带 datagen connector
- **Week 2+（jdbc 等）**：使用自定义 Dockerfile，在镜像层面 COPY JAR，不要用 volumes 覆盖
