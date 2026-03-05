# LLM API 配置指南

> 上次更新：2026-03-05
> 本项目通过 `langchain-openai` 接入 LLM，兼容所有支持 OpenAI 格式的 API 服务。

---

## 推荐方案：OpenRouter

[OpenRouter](https://openrouter.ai) 是一个 LLM API 聚合平台，支持 DeepSeek、Claude、GPT 等主流模型，无地区限制。

### 配置步骤

1. 注册 OpenRouter 账号并获取 API Key：https://openrouter.ai/keys

2. 在 `.env` 中配置：

```bash
LLM_API_KEY=sk-or-xxxx        # OpenRouter API Key
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-chat   # 见下方模型选择
```

### 模型选择建议

| 模型 | 推荐场景 | 成本 |
|------|---------|------|
| `deepseek/deepseek-chat` | 默认选择，SQL 生成效果好，性价比最高 | 低 |
| `anthropic/claude-3.5-sonnet` | 复杂推理、Java 代码生成（Phase 2） | 中高 |
| `openai/gpt-4o-mini` | 快速响应，简单 SQL | 低 |

---

## 备选方案：直接使用兼容 API

任何兼容 OpenAI 格式的 API 均可直接配置，无需改代码：

```bash
# 示例：本地 Ollama
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:14b

# 示例：Azure OpenAI
LLM_API_KEY=your-azure-key
LLM_BASE_URL=https://your-resource.openai.azure.com/openai/deployments/your-deployment
LLM_MODEL=gpt-4o
```

---

## 后端代码中的使用方式

`langchain-openai` 会自动读取这些环境变量：

```python
import os
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model=os.environ["LLM_MODEL"],
    api_key=os.environ["LLM_API_KEY"],
    base_url=os.environ["LLM_BASE_URL"],
    temperature=0,          # SQL 生成用 0，保证确定性
    streaming=True,         # WebSocket 流式输出
)
```

---

## 注意事项

- **Temperature 设为 0**：SQL 生成任务不需要创造性，0 减少随机语法错误
- **不要在代码里硬编码 API Key**，始终通过环境变量读取
- OpenRouter 按 Token 计费，开发阶段注意设置用量上限（OpenRouter 控制台可设置）
