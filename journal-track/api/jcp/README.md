# JCP（Journal of Computational Physics）新论文监控订阅 Agent

Elsevier 期刊「Crossref 发现 + Elsevier Abstract 摘要」方案的完整实现。
基于 agentmail 邮件系统，自动监控 JCP 新论文，撰写中文摘要，按订阅列表分发。

## 架构

```
Crossref API (发现层，免费)
    ↓ 按 created 倒序拉最近论文，DOI 去重
    ↓
pending 池（abstract 暂空也没关系）
    ↓
Elsevier Abstract API (摘要层，需 API Key)
    ↓ 对 pending 里没摘要的逐篇重试，curl 绕 TLS 指纹
    ↓
ready 判定（有摘要 = ready）
    ↓ ready≥10 或 满7天 触发
    ↓
LLM 撰写中文摘要 → 逐封邮件群发 → mark-sent
```

## 为什么不用 Scopus Search（重要踩坑）

elsevier-guide.md 原方案是 Scopus Search 发现 + Abstract API 摘要。实测发现 **Scopus 的 `prism:coverDate` 是纸质卷期分配日期，不是录用时间**：

- coverDate 可以指向未来（2026-12-01）或过去
- 按 `sort=coverDate:desc` 排出来的顺序无真实时序逻辑
- 订阅者会看到"去年的论文"混在新论文里

**解决办法**：发现层改用 Crossref 的 `created` 字段（Elsevier 向 Crossref 提交元数据的时间），这才是接近真实录用的时间。

## 摘要滞后窗口（第二个坑）

Elsevier Abstract API 对刚录用的论文返回 `RESOURCE_NOT_FOUND`。实测滞后约 **10 天**——论文先被 Crossref 收录，要等正式上线后摘要才进入 Elsevier 索引。

**解决办法**：
- 新论文先入 pending（摘要为空也收）
- 每次 collect 对 pending 里没摘要的重试 Abstract API
- 触发判定只看 **ready 数**（有摘要的），不用 pending 总数
- 滞后窗口内的论文会随时间逐渐变 ready

## TLS 指纹 vs 响应截断（两个相反的坑）

| 数据源 | 问题 | 解法 |
|---|---|---|
| Elsevier Abstract API | urllib 被 TLS 指纹降级（HTTP 200 但字段缺失） | 用 **curl** 子进程 |
| Crossref（大响应） | curl 在长响应时截断（json 解析报 unterminated string） | 用 **urllib** |

两个坑正好相反：Crossref 用 urllib，Elsevier 用 curl。

## 文件清单

| 文件 | 说明 |
|---|---|
| `jcp_check.py` | 论文检测与触发判定（Crossref + Elsevier Abstract） |
| `duty_wait.py` | 邮件值守脚本（阻塞等新邮件，Basic Auth） |
| `jcp_state.json` | 检测状态（seen/pending/last_check/last_sent/last_digest） |
| `jcp_followers.json` | 订阅列表 |
| `jcp_last_digest.txt` | 最近一期摘要正文（群发内容 + 欢迎信附件） |

## 部署步骤

### 前置条件
- Python 3（仅标准库）
- curl（系统自带）
- agentmail 账号 + MCP gateway
- Elsevier API Key（dev.elsevier.com 免费申请）

### 1. 配置 jcp_check.py

```python
ISSN = "0021-9991"           # JCP ISSN
JOURNAL_NAME = "Journal of Computational Physics"
# 迁移到其他 Elsevier 期刊：改这两个值即可
```

### 2. 初始化基线

```bash
python jcp_check.py --api-key YOUR_KEY --init
```

拉 Crossref 最近 80 篇入 seen，取摘要，生成 jcp_state.json 和 jcp_last_digest.txt。

### 3. 建空订阅列表

```json
{"followers": []}
```

### 4. 撰写首期摘要

```bash
python jcp_check.py --api-key YOUR_KEY --digest  # 导出 last_digest（JSON Lines）
```

LLM 读取导出内容，撰写中文摘要，存为 jcp_last_digest.txt。

### 5. 自检

```bash
python jcp_check.py --api-key YOUR_KEY  # 应返回 new=0, ready>0, due=false
```

### 6. 进入值守循环

```bash
# 阻塞等邮件（收到即退出 exit 0，超时 exit 2）
python duty_wait.py <server_url> <address> <password> <since_id> 21600 30
```

agent 在每次 duty_wait 唤醒后：
1. 处理邮件（订阅/退订）
2. 若距 last_check 满 24h，跑 `jcp_check.py` collect
3. 若 due，撰写中文摘要 → mark-sent → 群发
4. 重启下一轮 duty_wait

## jcp_check.py 用法

```bash
python jcp_check.py --api-key YOUR_KEY          # collect：检测+触发判定
python jcp_check.py --api-key YOUR_KEY --init    # 初始化基线
python jcp_check.py --api-key YOUR_KEY --pending  # 导出 pending（JSON Lines）
python jcp_check.py --api-key YOUR_KEY --digest   # 导出 last_digest
python jcp_check.py --api-key YOUR_KEY --mark-sent  # 标记已发送
```

collect 输出示例：
```json
{"new": 2, "refilled": 1, "pending": 5, "ready": 3, "last_sent": "...", "due": false, "reason": null}
```

## 配置参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `SEND_THRESHOLD` | 10 | ready 满 N 篇触发群发 |
| `SEND_DAYS` | 7 | 距上次满 N 天触发 |
| `MAX_ENRICH` | 40 | 每轮最多取摘要数（覆盖滞后窗口） |
| `FETCH_ROWS` | 80 | Crossref 每次拉取条数（~30 天） |

## 迁移到其他 Elsevier 期刊

改 `ISSN` 和 `JOURNAL_NAME`，其余零改动。前提：期刊被 Crossref 索引（绝大多数都是）。

## 凭证纪律

- API Key、密码、access_code **永不落盘**
- 脚本通过命令行参数接收凭证
- 本仓库不含任何真实凭证

## 已知限制

- 摘要最长延迟 ~10 天（等 Elsevier 索引跟上）
- Crossref 偶尔返回 Editorial/Corrigendum 等非研究论文（可按 type 进一步过滤）
- 会话死亡则值守停止（状态不丢，重启即恢复）
