# journal-track —— 期刊论文追踪订阅服务

## 目录结构

```
journal-track/
├── README.md                    # 本文件
├── psst/                        # IOP RSS 方案
│   ├── README.md
│   ├── journal-tracking-implementation.md  # 部署文档（通用模板）
│   ├── duty_wait.py
│   ├── psst_check.py
│   └── psst_last_digest.txt     # 示例摘要
├── jcp/                         # Crossref + Elsevier API
│   ├── README.md
│   ├── elsevier-guide.md        # Elsevier 适配指南
│   ├── jcp_check.py
│   └── duty_wait.py
├── actaastr/                    # Crossref + Elsevier API v2
│   ├── README.md
│   └── acta_check.py
└── pop/                         # 待建设
```

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
