#!/usr/bin/env python3
"""PSST (Plasma Sources Sci. Technol.) 新文章收集与群发触发判定。

用法:
  python3 psst_check.py --init       # 基线：当前 feed 记为已见，清空待发，last_sent=now，
                                     #   并把当前 feed 文章存入 last_digest（供新订阅者）
  python3 psst_check.py              # 收集：新文章并入 pending，打印状态 JSON
  python3 psst_check.py --pending    # 打印 pending 中全部文章 (JSON Lines)
  python3 psst_check.py --digest     # 打印 last_digest（最近一期的文章集合）
  python3 psst_check.py --mark-sent  # pending -> last_digest，清空 pending，last_sent=now

触发规则（due）：pending >= SEND_THRESHOLD 篇，或 pending 非空且距 last_sent >= SEND_DAYS 天。
状态文件: psst_state.json {"seen":[doi], "pending":[item], "last_check":iso, "last_sent":iso}
退出码: 0 = 成功, 1 = 抓取/解析失败(不更新状态)
"""
import sys, json, re, time, urllib.request, xml.etree.ElementTree as ET
from html import unescape

RSS_URL = "https://iopscience.iop.org/journal/rss/0963-0252"
STATE = "psst_state.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
SEND_THRESHOLD = 10
SEND_DAYS = 7

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def parse_iso(s):
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None

def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
            st.setdefault("pending", [])
            st.setdefault("last_sent", None)
            st.setdefault("last_digest", [])
            return st
    except Exception:
        return {"seen": [], "pending": [], "last_check": None, "last_sent": None, "last_digest": []}

def save_state(st):
    st["last_check"] = now_iso()
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)

def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", unescape(s)).strip()

def localname(tag):
    return tag.rsplit("}", 1)[-1]  # 忽略命名空间，兼容 RSS 2.0 与 RSS 1.0/RDF

def fetch_items():
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=30).read()
    root = ET.fromstring(raw)
    items = []
    for it in root.iter():
        if localname(it.tag) != "item":
            continue
        fields = {}
        for child in it:
            ln = localname(child.tag)
            if ln in ("title", "link", "description", "creator", "date", "doi", "citation"):
                fields.setdefault(ln, (child.text or "").strip())
        link = fields.get("link", "")
        m = re.search(r"(10\.1088/1361-6595/[A-Za-z0-9]+)", fields.get("doi", "") + " " + link)
        doi = m.group(1) if m else link
        items.append({
            "doi": doi,
            "title": strip_html(fields.get("title", "")),
            "authors": strip_html(fields.get("creator", "")),
            "link": link,
            "date": fields.get("date", ""),
            "abstract": strip_html(fields.get("description", ""))[:1200],
        })
    return items

def due_reason(st):
    n = len(st["pending"])
    if n >= SEND_THRESHOLD:
        return f"累计{n}篇满{SEND_THRESHOLD}篇"
    if n > 0:
        t = parse_iso(st.get("last_sent"))
        if t is not None and time.time() - t >= SEND_DAYS * 86400:
            return f"距上次群发已满{SEND_DAYS}天且有{n}篇待发"
    return None

def main():
    args = set(sys.argv[1:])
    st = load_state()

    if "--pending" in args:
        for it in st["pending"]:
            print(json.dumps(it, ensure_ascii=False), flush=True)
        return

    if "--digest" in args:
        for it in st.get("last_digest", []):
            print(json.dumps(it, ensure_ascii=False), flush=True)
        return

    if "--mark-sent" in args:
        n = len(st["pending"])
        if st["pending"]:
            st["last_digest"] = st["pending"]
        st["pending"] = []
        st["last_sent"] = now_iso()
        save_state(st)
        print(f"MARKED sent, cleared {n} pending, last_digest updated")
        return

    try:
        items = fetch_items()
    except Exception as e:
        print(f"[psst_check] fetch error: {e}", file=sys.stderr)
        sys.exit(1)
    if not items:
        print("[psst_check] no items in feed", file=sys.stderr)
        sys.exit(1)

    if "--init" in args:
        st["seen"] = sorted({it["doi"] for it in items})
        st["pending"] = []
        st["last_sent"] = now_iso()
        st["last_digest"] = items
        save_state(st)
        print(f"INIT ok: {len(items)} items baselined, last_sent=now, last_digest seeded")
        return

    seen = set(st["seen"])
    new = [it for it in items if it["doi"] not in seen]
    st["pending"].extend(new)
    st["seen"] = sorted(seen | {it["doi"] for it in new})
    reason = due_reason(st)
    save_state(st)
    print(json.dumps({
        "new": len(new), "pending": len(st["pending"]),
        "last_sent": st["last_sent"], "due": bool(reason), "reason": reason,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
