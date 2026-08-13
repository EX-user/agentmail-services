#!/usr/bin/env python3
"""
JCP (Journal of Computational Physics) 新论文检测与触发判定
—— 数据源：Crossref（发现）+ Elsevier Abstract API（摘要）

架构：
  第一步 Crossref：按 created 倒序拉最近论文，拿到真实入库时间
  第二步 Elsevier Abstract API：逐篇按 DOI 补摘要正文

用法:
  python jcp_check.py --api-key YOUR_KEY          # 收集模式（默认）
  python jcp_check.py --api-key YOUR_KEY --init    # 初始化基线
  python jcp_check.py --api-key YOUR_KEY --pending  # 导出 pending
  python jcp_check.py --api-key YOUR_KEY --digest   # 导出 last_digest
  python jcp_check.py --api-key YOUR_KEY --mark-sent  # 标记已发送
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

# === 配置 ===
ISSN = "0021-9991"  # JCP ISSN
JOURNAL_NAME = "Journal of Computational Physics"

# Crossref（发现层，无需 Key）
CROSSREF_URL = "https://api.crossref.org/journals/{issn}/works"

# Elsevier（摘要层，需要 Key）
ABSTRACT_URL = "https://api.elsevier.com/content/abstract/doi"

SEND_THRESHOLD = 10  # 累计满 N 篇（已就绪）触发群发
SEND_DAYS = 7  # 距上次满 N 天触发群发
MAX_ENRICH = 40  # 每轮最多取摘要的篇数（覆盖摘要滞后窗口）
FETCH_ROWS = 80  # Crossref 每次拉取条数（覆盖 ~30 天）

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jcp_state.json")
DIGEST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jcp_last_digest.txt")


# ============================================================
# 通用 HTTP（curl 子进程，绕 TLS 指纹问题）
# ============================================================
def fetch_json(url, headers=None):
    """用 curl 获取 JSON"""
    cmd = ["curl", "-s", "--max-time", "30", url]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if result.returncode != 0 or not result.stdout:
            return None
        return json.loads(result.stdout)
    except Exception as e:
        print(f"fetch_json error: {e}", file=sys.stderr)
        return None


# ============================================================
# 第一步：Crossref 论文发现
# ============================================================
def fetch_recent_articles():
    """Crossref 按 created 倒序拉最近论文"""
    import urllib.request
    url = (f"{CROSSREF_URL.format(issn=ISSN)}"
           f"?filter=type:journal-article"
           f"&rows={FETCH_ROWS}"
           f"&sort=created&order=desc")
    req = urllib.request.Request(url, headers={
        "User-Agent": "JCP-tracker/1.0 (mailto:your-agent@example.com)"
    })
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"fetch_recent_articles error: {e}", file=sys.stderr)
        return []

    items = data.get("message", {}).get("items", [])
    articles = []
    for it in items:
        doi = it.get("DOI", "")
        if not doi:
            continue

        # created 是真实的入库时间（ISO8601）
        created = it.get("created", {}).get("date-time", "")

        # 作者：Crossref 给的是列表，拼成字符串
        authors_list = it.get("author", [])
        authors = _format_authors(authors_list)

        # 标题
        title = (it.get("title", [""]) or [""])[0]

        # 卷期
        volume = it.get("volume", "")
        issue = it.get("issue", "")
        page = it.get("page", "")
        article_number = it.get("article-number", "")

        articles.append({
            "doi": doi,
            "title": title,
            "authors": authors,
            "created": created,  # 真实入库时间
            "volume": volume,
            "issue": issue,
            "page": page,
            "article_number": article_number,
            "link": it.get("URL", f"https://doi.org/{doi}"),
            "abstract": ""  # 待第二步填充
        })

    return articles


def _format_authors(authors_list):
    """Crossref author 列表 → 'A. Smith, Y. Wang'"""
    if not authors_list:
        return ""
    names = []
    for a in authors_list:
        given = a.get("given", "")
        family = a.get("family", "")
        if family:
            names.append(f"{given} {family}".strip())
    return ", ".join(names)


# ============================================================
# 第二步：Elsevier Abstract API 取摘要
# ============================================================
def fetch_abstract(api_key, doi, retries=3):
    url = f"{ABSTRACT_URL}/{doi}?httpAccept=application/json"
    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/json"
    }
    for attempt in range(retries):
        data = fetch_json(url, headers)
        if data:
            try:
                desc = data["abstracts-retrieval-response"]["coredata"]["dc:description"]
                desc = re.sub(r"<[^>]+>", "", desc)  # 去 HTML
                desc = re.sub(r"\s+", " ", desc).strip()
                return desc[:1200]
            except (KeyError, TypeError):
                pass
        if attempt < retries - 1:
            time.sleep(1)
    return ""


def enrich_with_abstracts(api_key, articles, max_enrich=MAX_ENRICH):
    enriched = []
    for i, article in enumerate(articles[:max_enrich]):
        abstract = fetch_abstract(api_key, article["doi"])
        enriched.append({**article, "abstract": abstract})
        if i < max_enrich - 1:
            time.sleep(1)  # polite
    return enriched


# ============================================================
# 状态文件
# ============================================================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "seen": [],
        "pending": [],
        "last_check": None,
        "last_sent": None,
        "last_digest": []
    }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def save_digest_file(articles):
    """保存 last_digest 到文本文件（供欢迎信引用）。只展示有摘要的论文。"""
    ready = [a for a in articles if a.get("abstract")]
    lines = [
        f"=== {JOURNAL_NAME} 最新一期 ===",
        f"整理时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"篇数: {len(ready)}",
        ""
    ]
    for i, a in enumerate(ready, 1):
        vol = a.get("volume", "")
        created = a.get("created", "")[:10]
        lines.append(f"[{i}] {a['title']}")
        lines.append(f"    作者: {a.get('authors','')}")
        lines.append(f"    录用: {created} | 卷{vol}")
        lines.append(f"    摘要: {a['abstract'][:300]}...")
        lines.append(f"    链接: {a['link']}")
        lines.append("")
    lines.append("---")
    lines.append("回复「关注」订阅，回复「取消关注」退订。")
    with open(DIGEST_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================
# 触发判定（只看"已就绪"= 有摘要的论文数）
# ============================================================
def _count_ready(pending):
    """pending 中已有摘要的篇数"""
    return sum(1 for a in pending if a.get("abstract"))


def _refill_abstracts(api_key, pending):
    """对 pending 里 abstract 为空的条目重试取摘要，返回成功填充数"""
    refilled = 0
    for a in pending:
        if not a.get("abstract"):
            ab = fetch_abstract(api_key, a["doi"], retries=1)
            if ab:
                a["abstract"] = ab
                refilled += 1
            time.sleep(1)  # polite
    return refilled


def _check_due(state):
    ready = _count_ready(state["pending"])
    if ready >= SEND_THRESHOLD:
        return True, f"已就绪{ready}篇满{SEND_THRESHOLD}篇"
    if ready > 0 and state["last_sent"]:
        last_sent_dt = datetime.fromisoformat(state["last_sent"].replace("Z", "+00:00"))
        days_since = (datetime.now(timezone.utc) - last_sent_dt).days
        if days_since >= SEND_DAYS:
            return True, f"距上次满{days_since}天（已就绪{ready}篇）"
    return False, None


# ============================================================
# 模式：init / collect / pending / digest / mark-sent
# ============================================================
def init(api_key):
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()
    try:
        articles = fetch_recent_articles()
        if articles:
            enriched = enrich_with_abstracts(api_key, articles)
            state["seen"] = [a["doi"] for a in articles]
            state["pending"] = []
            state["last_check"] = now
            state["last_sent"] = now
            state["last_digest"] = enriched
            save_digest_file(enriched)
        save_state(state)
        print(json.dumps({
            "status": "initialized",
            "seen_count": len(state["seen"]),
            "last_sent": state["last_sent"],
            "source": "crossref+elsevier"
        }, ensure_ascii=False))
    except Exception as e:
        print(f"init error: {e}", file=sys.stderr)
        sys.exit(1)


def collect(api_key):
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()
    try:
        articles = fetch_recent_articles()
        if not articles:
            print(json.dumps({"new": 0, "pending": len(state["pending"]),
                              "ready": _count_ready(state["pending"]),
                              "last_sent": state["last_sent"],
                              "due": False, "reason": None}))
            return

        new_articles = [a for a in articles if a["doi"] not in state["seen"]]

        if new_articles:
            enriched = enrich_with_abstracts(api_key, new_articles)
            state["pending"].extend(enriched)
            state["seen"].extend([a["doi"] for a in new_articles])

        # 对 pending 里还没摘要的重试填充（摘要滞后窗口内的论文会逐渐变 ready）
        refilled = _refill_abstracts(api_key, state["pending"])

        state["last_check"] = now
        due, reason = _check_due(state)
        save_state(state)
        print(json.dumps({
            "new": len(new_articles),
            "refilled": refilled,
            "pending": len(state["pending"]),
            "ready": _count_ready(state["pending"]),
            "last_sent": state["last_sent"],
            "due": due,
            "reason": reason
        }, ensure_ascii=False))
    except Exception as e:
        print(f"collect error: {e}", file=sys.stderr)
        sys.exit(1)


def export_pending():
    state = load_state()
    for a in state["pending"]:
        print(json.dumps(a, ensure_ascii=False))


def export_digest():
    state = load_state()
    for a in state["last_digest"]:
        print(json.dumps(a, ensure_ascii=False))


def mark_sent():
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()
    state["last_digest"] = state["pending"]
    state["pending"] = []
    state["last_sent"] = now
    save_state(state)
    save_digest_file(state["last_digest"])
    print(json.dumps({
        "status": "marked_sent",
        "last_sent": now,
        "digest_count": len(state["last_digest"])
    }, ensure_ascii=False))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="JCP 新论文检测 (Crossref + Elsevier)")
    parser.add_argument("--api-key", required=True, help="Elsevier API Key (用于摘要)")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--pending", action="store_true")
    parser.add_argument("--digest", action="store_true")
    parser.add_argument("--mark-sent", action="store_true")
    args = parser.parse_args()

    if args.init:
        init(args.api_key)
    elif args.pending:
        export_pending()
    elif args.digest:
        export_digest()
    elif args.mark_sent:
        mark_sent()
    else:
        collect(args.api_key)


if __name__ == "__main__":
    main()
