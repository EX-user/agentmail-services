# Elsevier 期刊新论文获取指南
## —— 从 API Key 申请到稳定拉取新论文 + 摘要

**适用场景**：想把"期刊监控订阅 Agent"模板（PSST 实现）迁移到 Elsevier 出版的期刊（如 Acta Astronautica、Aerospace Science and Technology、Journal of Spacecraft and Rockets 等 Elsevier 系刊物）。

**读者**：已读过 PSST 部署文档、了解值守循环与状态机架构，只想知道 Elsevier 数据源这一层怎么适配。

---

## 0. 与 PSST(RSS) 方案的本质差异（先看这张表）

| 维度 | PSST（IOP，RSS 方案） | Elsevier（API 方案） |
|---|---|---|
| **数据源** | 期刊 RSS feed（一条 URL） | Scopus Search API + Abstract Retrieval API |
| **是否需要凭证** | 不需要，匿名 GET | 必须有 API Key（X-ELS-APIKey 请求头） |
| **凭证获取** | 无 | 在 dev.elsevier.com 注册，创建 API Key（个人 Key 免费，有额度） |
| **新论文发现** | 一次 GET 解析 RSS XML，条目自带 title/link/doi/description | 一次 Scopus Search 拿列表（含 doi/title/作者/卷期），**不含摘要正文** |
| **摘要获取** | RSS 的 description 字段直接可用 | **必须逐篇二次调** Abstract Retrieval API |
| **每轮 API 调用数** | 1 次（RSS） | 1 + N 次（1 次 Search + N 次 Abstract） |
| **反爬/合规风险** | 极低（RSS 为机器订阅设计） | 低（官方 API，但受 Key 额度与权限档位约束） |
| **主要故障模式** | RSS 改版、命名空间变化 | Key 过期/额度耗尽、TLS 指纹降级、view 参数陷阱、摘要偶发空返回 |

**一句话**：RSS 是"开箱即用的自助餐"，Elsevier API 是"凭票点菜，且票的等级决定你能点几道、点到什么"。

---

## 1. 申请 API Key（PSST 不需要的步骤）

Elsevier 所有 API 调用都要 API Key，这是与 RSS 方案最大的前置差异。

**步骤**：
1. 访问 https://dev.elsevier.com → 注册账号（用机构邮箱可能拿到更高权限，个人邮箱也能拿到基础 Key）
2. 登录后进入 "My API Key" → "Add API Key"
3. 填写应用名（随意，如 "journal-tracker"），接受条款
4. 生成形如 `15bf5dabba4745de0a678467c82a5e8f` 的 32 位十六进制 Key
5. **记下 Key**（页面后续还能查，但建议自己存好）

**凭证纪律**（沿用 PSST 文档 §2.3）：
- API Key **不要落盘到代码仓库/文档/截图**。文档示例里用占位符 `YOUR_ELS_APIKey`
- 脚本运行时通过命令行参数或环境变量传入
- API Key 不如密码敏感（可重新生成吊销），但同样不应公开

**额度**：个人 API Key 有每周调用配额（Search API 约 5000/周，Abstract API 约 10000/周，具体看 dev.elsevier.com 的 quota 页）。对"每天 1 次 Search + 偶尔逐篇取摘要"的监控场景，额度绰绰有余。

---

## 2. 两步式数据获取（核心架构差异）

PSST 一次 RSS GET 就拿到全部信息；Elsevier 必须**两步**：

### 第一步：Scopus Search API —— 发现新论文（列表）

```
GET https://api.elsevier.com/content/search/scopus
    ?query=ISSN({ISSN})        # 按期刊 ISSN 过滤
    &date={YYYY-YYYY}          # 年份范围（注意：只支持年份，见 §4）
    &sort=coverDate:desc       # 按出版日期倒序
    &count=25                  # 每页条数
    &httpAccept=application/json
请求头: X-ELS-APIKey: {你的Key}
       Accept: application/json
```

返回的每条 entry 含：`prism:doi`（去重键）、`dc:title`、`dc:creator`、`prism:coverDate`、`prism:volume`、`prism:pageRange`、`link`。

**关键**：**Scopus Search 即使在 query 里指定 `field=dc:description`，对个人 Key 也不返回摘要正文**。

ISSN 怎么找：期刊主页（如 https://www.sciencedirect.com/journal/acta-astronautica）底部有 ISSN，或 Scopus 期刊页查。Acta Astronautica 是 `0094-5765`。

### 第二步：Abstract Retrieval API —— 逐篇取摘要

对第一步拿到的每个 DOI：

```
GET https://api.elsevier.com/content/abstract/doi/{DOI}?httpAccept=application/json
请求头: X-ELS-APIKey: {你的Key}
       Accept: application/json
```

摘要正文在返回 JSON 的 `abstracts-retrieval-response.coredata.dc:description`（可能含 HTML 标签，需 `re.sub(r"<[^>]+>", "", text)` 清理）。

**调用频率建议**：每篇之间间隔 >=1 秒（polite），且对一批新文章设上限（如 enrich_with_abstracts 的 max_enrich=15），避免短时大量请求触发限流。

---

## 3. 三个 Elsevier 专属的坑（PSST 不会遇到）

### 坑 1（最重要）：Python urllib 会被 TLS 指纹降级

**症状**：用 Python urllib 请求 Abstract API，返回 HTTP 200，但 coredata 里**没有 `dc:description` 键**——摘要被静默裁掉了。同一 URL 用 curl 请求则正常返回完整摘要（170KB vs 2.6KB）。

**根因**：Elsevier 服务端按 TLS 指纹（JA3）区分客户端，对非 curl/非浏览器的指纹走降级路径。加 `User-Agent: curl/...` 头没用（指纹在 TLS 层，不在 HTTP 头层）。

**实测**：urllib 连续 10 次取摘要 0/10 成功，curl 5/5 成功。

**解法**：`fetch_json` 改用 `subprocess.run(["curl", ...])`。这不是优雅的解法，但是唯一稳定的解法。Windows 上 curl 也预装（实测可用）。

```python
def fetch_json(url, headers):
    cmd = ["curl", "-s", "--max-time", "30", url]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
    if result.returncode != 0 or not result.stdout:
        return None
    return json.loads(result.stdout)
```

### 坑 2：Abstract API 的 view 参数陷阱

**直觉**：想拿完整数据 → 加 `view=FULL`。**这个直觉对个人 API Key 是错的**。

| view 参数 | 结果 |
|---|---|
| `view=FULL` | **401 Unauthorized**（个人 Key 权限不足，FULL 需机构 entitlement） |
| `view=META` | 200，但无 `dc:description` |
| **不带 view** | **200，含 `dc:description`**（但受坑 1 的指纹问题影响） |

**解法**：URL 里**不要带 view 参数**。代码里也别写 `view=FULL`。

### 坑 3：摘要偶发空返回（服务端波动）

同一 DOI、同一请求，Elsevier 服务端**偶尔**返回空 `dc:description`（非指纹问题，是负载均衡到不同节点的数据不一致）。频率不高但会出现。

**解法**：`fetch_abstract` 加 retries=3，每次空返回后 sleep(1) 重试。

---

## 4. Elsevier date 参数的粒度限制

Scopus Search 的 `date` 参数**只支持年份**：
- `date=2026` —— 2026 年
- `date=2024-2026` —— 2024 至 2026 年

**不支持**精确日期（如 `from=2026-08-01`）。这与 Crossref API 不同。

**影响**：如果想"只看最近 7 天的新文章"，不能在 query 层面限定，必须：
1. query 用 `date={去年}-{今年}` 拿近两年全部
2. 拿到结果后本地按 `prism:coverDate` 字段过滤

对监控场景影响不大（反正每天全量比对 + DOI 去重），但要知道这个限制。

## 4.1 重大发现：Scopus coverDate ≠ 真实录用时间（JCP 实测）

**问题**：Scopus Search 返回的 `prism:coverDate` 是**纸质卷期分配日期**，不是上线/录用时间。它可以是未来日期（如 2026-12-01），按 `coverDate:desc` 排序拿到的不是"最新录用"的论文。

**对照实验**：改用 Crossref 的 `created` 字段（Elsevier 向 Crossref 提交元数据的时间，接近真实录用），日期才合理——最近 15 篇都是 2026-08-07~08-13 录入的。

**推荐架构**（所有 Elsevier 期刊）：
1. **发现层**：Crossref `created` 倒序（urllib 可用，无 TLS 问题）
2. **摘要层**：Elsevier Abstract API 逐篇取（curl 绕 TLS 指纹）
3. **滞后窗口**：新录用论文（约 10 天内）Abstract API 返回 `RESOURCE_NOT_FOUND`——pending 池中没摘要的条目每轮重试，只统计"有摘要的 ready 数"触发群发

**一句话**：Scopus 的 coverDate 用于"看卷期目录"可以，用于"追踪最新录用"不行。发现层用 Crossref created，摘要层用 Elsevier Abstract API。

**网络坑（方向相反，必须混用）**：
- Crossref 大响应（rows=40 约 500KB）必须用 urllib——curl 会截断导致 JSON 解析报 "unterminated string"
- Elsevier Abstract API 必须用 curl——urllib 被 TLS 指纹降级
- 两个坑方向正好相反，组合使用：urllib 拉 Crossref，curl 拉 Elsevier

**推荐架构**（ActaAstr v2 + JCP 已实测通过）：
- 发现层：Crossref `created` 倒序（urllib）
- 摘要层：Elsevier Abstract API（curl，retries=3）
- 触发判定：只统计 ready 数（有摘要的），非 pending 总数
- 每次 collect 对 pending 里 abstract 为空的条目重试

---

## 5. 认证失败的处理（Key 相关故障）

PSST 的 RSS 不涉及鉴权；Elsevier 每次调用都带 Key，Key 相关故障是新增的故障类别：

| 错误 | 症状 | 处理 |
|---|---|---|
| **Key 无效/拼错** | 所有请求 401 `AUTHENTICATION_ERROR` | 核对 Key，到 dev.elsevier.com 重新查 |
| **Key 额度耗尽** | 429 或 `QUOTA_EXHAUSTED` | 等周配额重置，或申请提升额度 |
| **Key 权限档位不足** | 401 `Requestor configuration settings insufficient` | 个人 Key 拿不到全文，只能拿摘要——监控场景只需摘要 |
| **Key 被吊销** | 所有请求 401 | 重新生成 Key |

**监控脚本的应对**：fetch_json 返回 None 或解析出错误响应时，collect 模式 **exit 1 且状态零改动**（沿用 PSST 文档的失败保护铁律）。

---

## 6. 最小可行流程（迁移清单）

1. **申请 API Key**（§1）
2. **找目标期刊 ISSN**（期刊主页底部）
3. **改 acta_check.py 的配置**：`API_KEY`、`ISSN`、`SEARCH_URL`、`ABSTRACT_URL`
4. **fetch_json 改 curl 版**（§3 坑 1）
5. **fetch_abstract 不带 view 参数 + 重试**（§3 坑 2、3）
6. **fetch_recent_articles 用 Scopus Search**（§2 第一步），`date` 用年份范围（§4）
7. **enrich_with_abstracts 逐篇取摘要**（§2 第二步），注意 polite 间隔
8. **--init 初始化基线**，验证种子文章摘要获取率（应为 100%）
9. 其余（duty_wait / 状态机 / 分发 / 触发逻辑）**零改动**

---

## 7. 适用范围与边界

**适用**：Elsevier 出版的、被 Scopus 索引的期刊（绝大多数 Elsevier 期刊都是）。

**不适用**：
- 期刊未被 Scopus 索引 → 需改用期刊官网 RSS 或 Crossref
- 需要全文 → 个人 API Key 权限不够，需机构订阅 + insttoken
- 非 Elsevier 的 RSS 期刊 → 直接用 PSST 的 RSS 方案

---

*代码来源：follow_me_for_latest_ActaAstr@mailofagents.online*
*与 acta_check.py 配套使用。*
