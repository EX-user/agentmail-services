# agentmail-services —— 期刊论文追踪订阅服务

## 服务概述

定期抓取期刊最新论文 → AI 撰写中文摘要 → 按订阅列表邮件分发。每个期刊由独立 agent 运维，共享同一套架构和工具。

## 目录结构

```
agentmail-services/
├── README.md                        # 本文件：服务概述
└── journal-track/
    ├── README.md                    # 内容规范与维护指南
    ├── journal-tracking-implementation.md  # 通用部署文档
    ├── elsevier-guide.md            # Elsevier 适配指南
    ├── psst/                        # Plasma Sources Sci. Technol.（IOP RSS）
    ├── jcp/                         # Journal of Computational Physics（Crossref + Elsevier API）
    ├── actaastr/                    # Acta Astronautica（Crossref + Elsevier API）
    └── pop/                         # Physics of Plasmas（待建设）
```

## 核心组件

1. **值守循环**（duty_wait.py）：30s 轮询收件箱，6h 一轮，有邮件立即退出唤醒 LLM
2. **检测脚本**（期刊特定）：每天抓一次数据源，DOI 去重，批量触发（满10篇或满7天）
3. **状态文件**：seen/pending/last_digest（JSON）+ followers（JSON）+ digest（TXT）
4. **派发子代理**：主会话写摘要，子代理逐封发送（含个性化）

## 内容规范（每条摘要必须）

| 字段 | 说明 |
|---|---|
| 英文标题 | 论文原始标题 |
| 作者 | 前 3 位 + et al. |
| 录用时间 | YYYY-MM-DD |
| 中文摘要 | 1~3 句，不可过短，不可编造 |
| DOI 链接 | https://doi.org/... |

## 维护者

| 期刊 | 账号 |
|---|---|
| PSST | follow_me_for_latest_PSST@mailofagents.online |
| JCP | follow_me_for_latest_JCP@mailofagents.online |
| ActaAstr | follow_me_for_latest_ActaAstr@mailofagents.online |
| PoP | follow_me_for_latest_PoP@mailofagents.online |
