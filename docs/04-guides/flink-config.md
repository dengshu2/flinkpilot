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
