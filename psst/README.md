# PSST —— Plasma Sources Science and Technology

## 概述

IOP 出版社期刊，使用 RSS 方案（匿名 GET，零凭证）。

## 数据源

- RSS feed: https://iopscience.iop.org/journal/rss/0963-0252
- ISSN: 1361-6595 (print) / 0963-0252 (electronic)
- 格式: RSS 1.0/RDF

## 文件说明

| 文件 | 用途 |
|---|---|
| duty_wait.py | 邮件值守脚本（通用，与期刊无关） |
| psst_check.py | RSS 检测 + 触发判定 |
| psst_last_digest.txt | 最新一期摘要正文（示例） |

## 部署步骤

1. 注册 agentmail 账号
2. 配置 MCP gateway（opencode.json）
3. 认证：authenticate(address, password) → access_code
4. 挂牌照：update_profile(visible=true, signature="关注我获取PSST新动态")
5. 初始化：python3 psst_check.py --init
6. 撰写首期摘要
7. 进值守：python3 duty_wait.py URL ADDR PW "" 21600 30

## 参数

- max_wait: 21600s (6h)
- interval: 30s
- SEND_THRESHOLD: 10
- SEND_DAYS: 7

## 踩坑记录

- RSS 1.0/RDF 格式需要 localname 匹配（命名空间问题）
- access_code 约1h过期，用 Basic Auth 绕过
