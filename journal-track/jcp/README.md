# JCP —— Journal of Computational Physics

## 概述

Elsevier 出版社期刊，使用 Crossref + Elsevier API 方案。

## 数据源

- 发现层: Crossref API (sort=created，按录用时间排序)
- 摘要层: Elsevier Abstract API (curl 绕 TLS 指纹降级)
- ISSN: 0045-7930 (print) / 1090-2716 (online)

## 文件说明

| 文件 | 用途 |
|---|---|
| duty_wait.py | 邮件值守脚本（通用） |
| jcp_check.py | Crossref 发现 + Elsevier 摘要 |
| README.md | 本文件 |

## 踩坑记录

1. Scopus coverDate ≠ 真实录用时间（纸质卷期日期）
2. Elsevier Abstract API 滞后窗口（约10天）
3. Crossref 大响应必须用 urllib（curl 会截断）
4. Elsevier 必须用 curl（urllib 被 TLS 指纹降级）
