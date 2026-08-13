# agentmail-services

基于 MoA（Mail of Agents）邮件系统的各类服务。

## 目录结构

```
agentmail-services/
├── README.md                    # 本文件
└── journal-track/               # 期刊论文追踪订阅服务
    ├── README.md                # 服务概述与内容规范
    ├── psst/                    # Plasma Sources Sci. Technol.
    ├── jcp/                     # Journal of Computational Physics
    ├── actaastr/                # Acta Astronautica
    └── pop/                     # Physics of Plasmas（待建设）
```

## 各服务简介

### journal-track

定期抓取期刊最新论文 → AI 撰写中文摘要 → 按订阅列表邮件分发。

每个期刊由独立 agent 运维，共享同一套架构（值守循环 + 检测脚本 + 状态文件 + 派发子代理）。

维护者：见 journal-track/README.md
