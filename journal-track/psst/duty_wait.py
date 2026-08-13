#!/usr/bin/env python3
# 用法: python3 duty_wait.py <server_url> <address> <password> <since_id> [max_wait=300] [interval=30]
# 退出码: 0=有新邮件(打印 LAST_SEEN) 2=超时 1=异常。脚本退出即唤醒 LLM，故 max_wait 宜长（如 21600=6h）以省 token。
import sys, json, time, base64, urllib.request

def check_inbox(base, cred, since):
    url = base.rstrip("/") + "/api/inbox?limit=20"
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Basic " + cred)
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    newer, newest = [], since
    for m in data.get("messages", []):
        if m["id"] > since:
            newer.append(m)
        if m["id"] > newest:
            newest = m["id"]
    return newer, newest

def main():
    base, addr, pw, since = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    max_wait = int(sys.argv[5]) if len(sys.argv) > 5 else 300
    interval = int(sys.argv[6]) if len(sys.argv) > 6 else 30
    cred = base64.b64encode((addr + ":" + pw).encode()).decode()
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            newer, newest = check_inbox(base, cred, since)
            if newer:
                for m in newer:
                    print(json.dumps({"id": m["id"], "from": m.get("from",""),
                        "subject": m.get("subject",""), "preview": m.get("preview",""),
                        "unread": m.get("unread", False)}, ensure_ascii=False), flush=True)
                print("LAST_SEEN=" + newest, flush=True)
                sys.exit(0)
        except Exception as e:
            import sys as s2; print(f"[duty_wait] error: {e}", file=s2.stderr, flush=True)
        time.sleep(interval)
    print("TIMEOUT", flush=True)
    sys.exit(2)

if __name__ == "__main__":
    main()
