# JCP —— Journal of Computational Physics

## 概述

Elsevier 出版社期刊，使用 Crossref + Elsevier API 双层数据源方案。

与 PSST（RSS 方案）的本质差异：Elsevier 期刊的 RSS 不可靠，Scopus Search 的 coverDate 不是录用时间，因此发现层改用 Crossref 的 created 字段。

## 数据源

- 发现层: Crossref API (`sort=created&order=desc`，按真实录用时间排序)
- 摘要层: Elsevier Abstract API (逐篇按 DOI 取摘要)
- ISSN: 0021-9991 (print) / 1090-2716 (online)

## 文件说明

| 文件 | 用途 |
|---|---|
| duty_wait.py | 邮件值守脚本（通用，与期刊无关） |
| jcp_check.py | Crossref 发现 + Elsevier 摘要 + ready 等待机制 |
| jcp_last_digest.txt | 最新一期摘要正文（参考输出示例） |
| jcp-implementation.md | 极尽详细的部署与运维文档 |

## 部署步骤

1. 申请 Elsevier API Key（dev.elsevier.com，免费）
2. 注册 agentmail 账号
3. 配置 MCP gateway
4. 认证 + 挂牌照
5. 初始化：`python jcp_check.py --api-key YOUR_KEY --init`
6. 撰写首期摘要
7. 进值守：`python duty_wait.py URL ADDR PW "" 21600 30`

## 参数

- max_wait: 21600s (6h)
- interval: 30s
- SEND_THRESHOLD: 10 (ready 篇数)
- SEND_DAYS: 7
- FETCH_ROWS: 80 (Crossref 拉取条数，覆盖 ~30 天)
- MAX_ENRICH: 40 (每轮最多取摘要数)

## 踩坑记录

1. Scopus `prism:coverDate` ≠ 真实录用时间（纸质卷期日期，可指向未来/过去）
2. Elsevier Abstract API 对新论文有 ~10 天滞后窗口（RESOURCE_NOT_FOUND）
3. Crossref 大响应必须用 urllib（curl 会截断 500KB+ 响应）
4. Elsevier 必须用 curl（urllib 被 TLS 指纹降级，HTTP 200 但字段缺失）
5. 两个坑方向相反：Crossref 用 urllib，Elsevier 用 curl
