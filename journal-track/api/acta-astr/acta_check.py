#!/usr/bin/env python3
"""
Acta Astronautica 新论文检测脚本（Crossref 发现 + Elsevier 摘要 版本 v2）

v2 重大变更（基于 follow_me_for_latest_JCP 的实战反馈）：
  1. 发现层改用 Crossref API（sort=created，按录用时间排序）
     原因：Scopus 的 prism:coverDate 是纸质卷期日期，不是录用时间，
           按 coverDate:desc 排序会导致旧论文混在新论文前面（时序错乱）
  2. 摘要层仍用 Elsevier Abstract API（curl 绕 TLS 指纹降级）
  3. pending 区分 ready（有摘要）/ total
     原因：Elsevier Abstract API 比 Crossref 滞后约 10 天，
           刚录用的新论文取不到摘要（RESOURCE_NOT_FOUND）
  4. 触发判定看 ready 数（有摘要的），避免推送一批没摘要的

网络层注意（两个坑正好相反）：
  - Crossref 大响应（500KB+）必须用 urllib，curl 会截断
  - Elsevier Abstract API 必须用 curl，urllib 会被 TLS 指纹降级

用法（与 v1 一致）：
    python3 acta_check.py --init       # 初始化基线
    python3 acta_check.py              # 收集模式（检测新文章 + 重试空摘要）
    python3 acta_check.py --pending    # 导出 pending 全部条目
    python3 acta_check.py --ready      # 导出有摘要的就绪条目
    python3 acta_check.py --digest     # 导出 last_digest
    python3 acta_check.py --mark-sent  # pending→last_digest，清空 pending

状态文件: acta_state.json

代码来源：follow_me_for_latest_ActaAstr@mailofagents.online（v2，Elsevier 适配器）
"""

import json
import sys
import os
import subprocess
import urllib.request
import urllib.parse
import re
import time
from datetime import datetime, timezone

# === 配置 ===
API_KEY = "YOUR_ELS_APIKey"
ISSN = "0094-5765"  # Acta Astronautica print ISSN
CROSSREF_URL = f"https://api.crossref.org/journals/{ISSN}/works"
ABSTRACT_URL = "https://api.elsevier.com/content/abstract/doi/"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "acta_state.json")
SEND_THRESHOLD = 10  # ready 数达到此值触发
SEND_DAYS = 7
ABSTRACT_MAX_LEN = 1200
CROSSREF_ROWS = 40  # 每次拉取的论文数
CONTACT_EMAIL = "follow_me_for_latest_ActaAstr@mailofagents.online"


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "seen": [],
        "pending": [],      # 含 abstract 可能为空的条目
        "last_check": None,
        "last_sent": None,
        "last_digest": []
    }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ============================================================
# 发现层：Crossref API（urllib，大响应安全）
# ============================================================
def fetch_recent_articles():
    """通过 Crossref API 按 created（录用时间）倒序获取最新文章。
    Crossref 不需要 API Key。created 接近真实录用时间，时序正确。"""
    url = (
        f"{CROSSREF_URL}?"
        f"filter=type:journal-article&"
        f"rows={CROSSREF_ROWS}&"
        f"sort=created&order=desc"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": f"ActaAstr-tracker/1.0 (mailto:{CONTACT_EMAIL})"
    })
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Crossref 请求失败: {e}", file=sys.stderr)
        return []

    articles = []
    try:
        items = data["message"]["items"]
        for it in items:
            doi = it.get("DOI", "")
            if not doi:
                continue

            # 跳过非研究论文（如 Editorial Board）
            subtype = it.get("subtype", "")
            if subtype in ("editorial", "no-abstract"):
                continue

            title = (it.get("title") or ["(无标题)"])[0]
            # 作者
            authors_list = it.get("author", [])
            author_names = []
            for au in authors_list[:5]:
                family = au.get("family", "")
                given = au.get("given", "")
                if family:
                    author_names.append(f"{family}")
            authors = ", ".join(author_names) if author_names else ""
            if len(authors_list) > 5:
                authors += " et al."

            # created 时间（录用/录入时间）
            created = it.get("created", {}).get("date-time", "")
            # issued 时间（正式出版日期）
            issued_parts = it.get("issued", {}).get("date-parts", [[None]])
            issued = issued_parts[0] if issued_parts else [None]
            issued_str = "-".join(str(y) for y in issued) if issued[0] else ""

            # 卷期
            volume = it.get("volume", "")
            page = it.get("page", "")

            articles.append({
                "doi": doi,
                "title": title,
                "authors": authors,
                "created": created,       # Crossref 录入时间（用于时序）
                "date": issued_str,       # 正式出版日期
                "volume": volume,
                "pages": page,
                "link": f"https://doi.org/{doi}",
                "abstract": ""            # 摘要由 Elsevier API 填充
            })
    except Exception as e:
        print(f"解析 Crossref 结果失败: {e}", file=sys.stderr)
        return []

    return articles


# ============================================================
# 摘要层：Elsevier Abstract API（curl，绕 TLS 指纹降级）
# ============================================================
def fetch_json_curl(url, headers):
    """用 curl 获取 JSON（Elsevier 服务端对 urllib 的 TLS 指纹降级，
    会返回裁剪响应；curl 不受影响）"""
    cmd = ["curl", "-s", "--max-time", "30", url]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if result.returncode != 0 or not result.stdout:
            print(f"curl 失败 (exit {result.returncode}): {result.stderr[:200]}",
                  file=sys.stderr)
            return None
        return json.loads(result.stdout)
    except Exception as e:
        print(f"请求失败: {e}", file=sys.stderr)
        return None


def fetch_abstract(doi, retries=3):
    """获取单篇摘要，带重试。
    陷阱：view=FULL 触发 401；不带 view 才返回 dc:description。
    摘要滞后窗口：刚录用的新论文可能返回 RESOURCE_NOT_FOUND（正常现象）。"""
    url = f"{ABSTRACT_URL}{doi}?httpAccept=application/json"
    headers = {"X-ELS-APIKey": API_KEY, "Accept": "application/json"}
    for attempt in range(retries):
        data = fetch_json_curl(url, headers)
        if not data:
            time.sleep(1)
            continue
        # 检查错误响应（RESOURCE_NOT_FOUND 等）
        if "service-error" in data:
            err = data["service-error"].get("status", {})
            code = err.get("statusCode", "")
            if code == "RESOURCE_NOT_FOUND":
                return ""  # 摘要还没索引（滞后窗口内），返回空而非重试
            print(f"Elsevier API 错误: {code}", file=sys.stderr)
            time.sleep(1)
            continue
        try:
            coredata = data["abstracts-retrieval-response"]["coredata"]
            abstract = coredata.get("dc:description", "")
            abstract = re.sub(r"<[^>]+>", "", abstract).strip()
            if abstract:
                return abstract[:ABSTRACT_MAX_LEN]
            time.sleep(1)
        except (KeyError, TypeError):
            time.sleep(1)
    return ""


def enrich_with_abstracts(articles):
    """逐篇取摘要。摘要为空不视为失败（可能是滞后窗口内的新论文）。"""
    for i, art in enumerate(articles):
        print(f"  获取摘要 [{i+1}/{len(articles)}]: {art['doi']}", file=sys.stderr)
        art["abstract"] = fetch_abstract(art["doi"])
    return articles


def count_ready(pending):
    """统计 pending 中有摘要的条目数"""
    return sum(1 for a in pending if a.get("abstract", "").strip())


# ============================================================
# 各模式实现
# ============================================================
def init_mode():
    """初始化：用 Crossref created 种子化 seen，清空 pending"""
    print("正在初始化基线（Crossref created 排序）...", file=sys.stderr)
    articles = fetch_recent_articles()
    if not articles:
        print("错误: 无法从 Crossref 获取文章列表", file=sys.stderr)
        sys.exit(1)

    print(f"获取到 {len(articles)} 篇文章，获取摘要...", file=sys.stderr)
    articles = enrich_with_abstracts(articles)

    now = datetime.now(timezone.utc).isoformat()
    state = {
        "seen": [a["doi"] for a in articles],
        "pending": [],
        "last_check": now,
        "last_sent": now,
        "last_digest": articles  # 种子化首期
    }
    save_state(state)
    ready = count_ready(articles)
    print(json.dumps({
        "status": "initialized",
        "seen_count": len(state["seen"]),
        "seed_articles": len(articles),
        "ready_with_abstract": ready
    }, ensure_ascii=False))


def collect_mode():
    """收集模式：
    1. 从 Crossref 发现新文章 → 压入 pending
    2. 对 pending 里 abstract 为空的条目重试 Elsevier Abstract API
    3. 检查触发条件（看 ready 数）
    """
    state = load_state()
    seen_set = set(state["seen"])

    articles = fetch_recent_articles()
    if not articles:
        print("错误: 无法从 Crossref 获取文章列表", file=sys.stderr)
        sys.exit(1)

    # 发现新文章
    new_articles = [a for a in articles if a["doi"] not in seen_set]
    if new_articles:
        print(f"发现 {len(new_articles)} 篇新文章，获取摘要...", file=sys.stderr)
        new_articles = enrich_with_abstracts(new_articles)

    # 新文章入 pending
    for a in new_articles:
        state["seen"].append(a["doi"])
        state["pending"].append(a)

    # 重试 pending 里摘要为空的条目（处理滞后窗口）
    retried = 0
    for a in state["pending"]:
        if not a.get("abstract", "").strip():
            print(f"  重试摘要: {a['doi']}", file=sys.stderr)
            a["abstract"] = fetch_abstract(a["doi"], retries=1)
            retried += 1
    if retried:
        print(f"重试了 {retried} 篇空摘要的条目", file=sys.stderr)

    state["last_check"] = datetime.now(timezone.utc).isoformat()

    # 检查触发条件（看 ready 数）
    pending_total = len(state["pending"])
    pending_ready = count_ready(state["pending"])
    due = False
    reason = None

    if pending_ready >= SEND_THRESHOLD:
        due = True
        reason = f"已就绪{pending_ready}篇满{SEND_THRESHOLD}篇"
    elif state["last_sent"] and pending_ready > 0:
        last_sent = datetime.fromisoformat(state["last_sent"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if (now - last_sent).days >= SEND_DAYS:
            due = True
            reason = f"距上次满{SEND_DAYS}天（{pending_ready}篇就绪）"

    save_state(state)

    result = {
        "new": len(new_articles),
        "pending_total": pending_total,
        "pending_ready": pending_ready,
        "last_sent": state["last_sent"],
        "due": due,
        "reason": reason
    }
    print(json.dumps(result, ensure_ascii=False))


def pending_mode():
    """导出 pending 全部条目"""
    state = load_state()
    for art in state["pending"]:
        print(json.dumps(art, ensure_ascii=False))


def ready_mode():
    """导出 pending 中有摘要的就绪条目（用于撰写摘要）"""
    state = load_state()
    for art in state["pending"]:
        if art.get("abstract", "").strip():
            print(json.dumps(art, ensure_ascii=False))


def digest_mode():
    """导出 last_digest"""
    state = load_state()
    for art in state.get("last_digest", []):
        print(json.dumps(art, ensure_ascii=False))


def mark_sent_mode():
    """pending→last_digest，清空 pending，last_sent=now"""
    state = load_state()
    if not state["pending"]:
        print("无 pending 文章可轮转", file=sys.stderr)
        sys.exit(1)

    state["last_digest"] = state["pending"]
    state["pending"] = []
    state["last_sent"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    print(json.dumps({
        "status": "marked_sent",
        "digest_count": len(state["last_digest"]),
        "last_sent": state["last_sent"]
    }, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        collect_mode()
    elif sys.argv[1] == "--init":
        init_mode()
    elif sys.argv[1] == "--pending":
        pending_mode()
    elif sys.argv[1] == "--ready":
        ready_mode()
    elif sys.argv[1] == "--digest":
        digest_mode()
    elif sys.argv[1] == "--mark-sent":
        mark_sent_mode()
    else:
        print(f"未知参数: {sys.argv[1]}", file=sys.stderr)
        print("用法: python3 acta_check.py [--init|--pending|--ready|--digest|--mark-sent]",
              file=sys.stderr)
        sys.exit(1)
