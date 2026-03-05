---
description: 开始开发某个功能或修复任务前的标准流程
---

## 开始开发任务的标准流程

// turbo-all

1. 阅读 AI 上下文文件，了解项目约束
```bash
cat .agents/CONTEXT.md
```

2. 阅读当前进度，确认任务状态
```bash
cat docs/06-roadmap/progress.md
```

3. 阅读当前 Phase 的验收标准
```bash
cat docs/06-roadmap/phases.md
```

4. 根据任务类型，阅读对应的操作指南或架构文档（参考 CONTEXT.md 中的"按任务类型选读"表格）

5. 开始实现

6. 实现完成后，更新 progress.md 中对应的任务状态

7. 如果做了重要技术决策，在 docs/03-decisions/ 下创建或更新对应的 ADR 文件
