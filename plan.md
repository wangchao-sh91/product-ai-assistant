# AI Ops Knowledge Copilot Plan

## 1. 总体实施策略

项目采用“先闭环、后增强”的方式推进，优先完成一个可以演示、可以写简历、可以继续扩展的 MVP。实施顺序遵循：

1. 先打通知识入库和问答闭环
2. 再增强故障助手和多 Agent
3. 最后补齐评测、观测和简历材料

建议总周期为 4 周到 6 周。

考虑到该项目主要用于个人转型和简历展示，实施上采用“前后端分离 + 后端 2 到 3 个 Python 服务”的方案。服务拆分只围绕核心职责展开，避免引入复杂服务治理，把重点放在 RAG、Agent、入库、评测和可观测性闭环上。

## 2. 阶段划分

### 阶段 0：项目初始化

目标：

- 初始化仓库结构
- 明确技术栈和模块边界
- 搭建本地开发环境

输出物：

- Monorepo 目录结构
- Docker Compose
- 基础 README
- 环境变量模板

建议目录：

```text
product-ai-assistant/
  apps/
    web-ui/
    api-gateway/
    ai-orchestrator/
    ingestion-worker/
  packages/
    shared/
      python/
      openapi/
  infra/
    compose.yaml
  datasets/
  docs/
  scripts/
```

服务边界：

```text
web-ui:
  - 聊天页、引用展示、会话历史、导入入口、调试信息展示

api-gateway:
  - 对外 REST API、鉴权、会话、反馈、任务状态
  - 调用 ai-orchestrator，投递 ingestion-worker 异步任务

ai-orchestrator:
  - RAG 检索编排、多 Agent 工作流、Prompt、模型调用、Tracing

ingestion-worker:
  - 文档解析、切分、Embedding、索引写入、索引重建、批量评测
```

可选简化方案：

```text
如果首版时间不足，可以先合并 api-gateway 与 ai-orchestrator，保留 ingestion-worker 独立。
这样后端为 2 个服务，仍满足前后端分离和异步入库拆分目标。
```

原单体模块可映射为：

```text
product-ai-assistant/
  apps/api-gateway/
    app/
  apps/ai-orchestrator/
    agents/
    retrieval/
    evals/
  apps/ingestion-worker/
    ingestion/
    jobs/
  apps/web-ui/
  datasets/
  docs/
  scripts/
  infra/
```

任务清单：

- 创建前端、API Gateway、AI Orchestrator、Ingestion Worker 子目录
- 配置 PostgreSQL、Redis、Qdrant、MinIO
- 约定公开 API、内部 API、任务消息和配置文件规范
- 明确服务间调用方式：同步问答走 HTTP，耗时入库和评测走 Redis 队列

### 阶段 1：知识库入库 MVP

目标：

- 让文档可以被导入、解析、切分并建立索引

输出物：

- 文档导入接口
- 文档解析模块
- Chunk 和 metadata 生成逻辑
- 向量索引写入逻辑
- 异步任务状态查询接口

任务清单：

- 支持 Markdown、PDF、TXT 三类文档
- 实现 parent-child chunking
- 设计 documents 和 document_chunks 表
- 接入向量模型与 Qdrant
- 实现重建索引脚本
- API Gateway 提供上传与任务查询接口
- Ingestion Worker 执行解析、切分、索引写入

完成标准：

- 至少导入 50 篇文档
- 能查询文档和 chunk 元数据

### 阶段 2：RAG 问答 MVP

目标：

- 打通从提问到回答的基础 RAG 流程

输出物：

- `/api/chat` 问答接口
- 检索、重排、生成链路
- 引用来源展示
- Web UI 聊天页

任务清单：

- 实现 query rewrite
- 实现 dense retrieval
- 增加 sparse retrieval 或 BM25
- 接入 reranker
- 返回答案、引用文档、证据片段
- API Gateway 保存会话与消息
- AI Orchestrator 负责 RAG 编排并返回结构化结果
- Web UI 展示答案、引用和检索证据

完成标准：

- 20 条标准问答样例中大部分能给出可接受答案
- 答案包含清晰引用

### 阶段 3：故障助手与多 Agent

目标：

- 将项目从“知识问答”升级为“故障 Copilot”

输出物：

- Router Agent
- Retriever Agent
- Incident Analyst Agent
- 简单故障分析工作流

任务清单：

- 抽象 Agent state
- 实现路由逻辑
- 为故障问题设计 prompt 模板
- 引入历史事故/Runbook 样例数据
- 输出根因猜测、排查步骤、引用依据

完成标准：

- 10 条故障场景样例可输出结构化排查建议

### 阶段 4：观测与评测

目标：

- 证明系统不是“看起来能跑”，而是“可以评估和优化”

输出物：

- tracing 集成
- 检索调试接口
- eval 数据集
- 自动评测脚本

任务清单：

- 记录 query rewrite、召回结果、重排结果
- 记录耗时、token、失败原因
- 构建问答与故障场景评测集
- 输出 Recall@K、命中率、引用覆盖率

完成标准：

- 能重复执行评测并查看指标变化

### 阶段 5：展示与简历包装

目标：

- 完成项目展示材料与简历表述

输出物：

- 演示脚本
- 架构图
- 核心流程图
- 简历项目描述
- 项目截图

任务清单：

- 整理 3 到 5 个 demo 场景
- 录制短演示视频或 GIF
- 输出简历中的项目摘要和技术亮点

## 3. 优先级排序

### P0

- 文档入库
- 向量检索
- 问答接口
- 引用展示

### P1

- Hybrid Retrieval
- Rerank
- Router Agent
- Incident Analyst Agent

### P2

- Critic Agent
- 变更影响分析
- 前端优化
- 权限体系

## 4. 里程碑计划

### 第 1 周

- 初始化仓库
- 搭建 web-ui、api-gateway、ai-orchestrator、ingestion-worker 基础服务
- 完成服务间调用契约与文档入库原型

### 第 2 周

- 完成基础 RAG 问答
- 实现引用返回
- 准备第一批样本文档

### 第 3 周

- 引入 Hybrid Retrieval 和 Rerank
- 提升检索准确率
- 完成 Debug 检索接口

### 第 4 周

- 实现多 Agent 路由与故障分析
- 准备故障场景数据
- 输出排查建议结果

### 第 5 周

- 接入 tracing 与评测
- 调优 Prompt、Chunk 和检索参数

### 第 6 周

- 补充前端展示
- 整理架构文档、演示素材和简历描述

## 5. 建议的 Monorepo 任务拆分

### web-ui

- 聊天页
- 引用来源卡片
- 会话历史
- 导入任务状态
- 检索调试信息展示

### api-gateway

- 用户会话接口
- 问答接口
- 反馈接口
- 简单鉴权
- 知识库导入入口
- 任务状态接口
- 内部服务调用封装

### ai-orchestrator

- Agent 编排
- retriever
- reranker
- answer composer
- tracing
- eval runner API

### ingestion-worker

- 文档导入异步任务
- 索引重建任务
- 评测批处理任务
- 文档解析与 chunk 生成
- 向量库写入

### datasets

- knowledge docs
- incident samples
- eval cases

## 6. 每阶段可交付成果

### 交付物 1

- 文档导入与索引能力

### 交付物 2

- 可演示的知识问答 API/UI

### 交付物 3

- 多 Agent 故障助手

### 交付物 4

- 评测与 tracing 能力

### 交付物 5

- 可写入简历的完整项目材料

## 7. 风险控制建议

- 首版不要同时做太多数据源接入，优先把高质量样本文档做扎实
- 多 Agent 不要一开始做太复杂的自治协作，优先做可控编排
- 前端不要成为主阻塞项，早期可先用 Swagger 或简单聊天页替代
- 如果模型成本敏感，可先用较小模型调通流程，再切换更强模型做演示

## 8. 下一步建议

按最小投入和最大产出排序，建议你下一步直接开始以下工作：

1. 建立 Monorepo 目录骨架
2. 先实现 backend 的 ingestion 与 retrieve 原型
3. 准备一批高质量样本文档和故障样例
4. 打通一个可回答、有引用的 MVP 闭环
