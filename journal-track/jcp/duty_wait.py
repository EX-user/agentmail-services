#!/usr/bin/env python3
"""
邮件值守脚本 - 阻塞等待新邮件

用法:
  python3 duty_wait.py <server_url> <address> <password> <since_id> [max_wait=21600] [interval=30]

退出码:
  0 = 有新邮件
  2 = 超时
  1 = 参数错误
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone


def check_inbox(server_url, address, password, since_id):
    """检查收件箱，返回新邮件列表"""
    url = f"{server_url}/api/inbox?limit=20"

    # Basic Auth
    import base64
    credentials = base64.b64encode(f"{address}:{password}".encode()).decode()

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {credentials}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            messages = data.get("messages", [])

            # 过滤新邮件（id > since_id）
            new_messages = []
            for msg in messages:
                msg_id = msg.get("id", "")
                if msg_id and (not since_id or msg_id > since_id):
                    new_messages.append(msg)

            return new_messages
    except Exception as e:
        print(f"check_inbox error: {e}", file=sys.stderr)
        return []


def main():
    if len(sys.argv) < 5:
        print("Usage: duty_wait.py <server_url> <address> <password> <since_id> [max_wait=21600] [interval=30]")
        sys.exit(1)

    server_url = sys.argv[1]
    address = sys.argv[2]
    password = sys.argv[3]
    since_id = sys.argv[4] if len(sys.argv) > 4 else ""
    max_wait = int(sys.argv[5]) if len(sys.argv) > 5 else 21600
    interval = int(sys.argv[6]) if len(sys.argv) > 6 else 30

    start_time = time.time()
    last_seen = since_id

    while True:
        elapsed = time.time() - start_time
        if elapsed >= max_wait:
            print("TIMEOUT", file=sys.stderr)
            sys.exit(2)

        new_messages = check_inbox(server_url, address, password, last_seen)

        if new_messages:
            # 打印新邮件
            for msg in new_messages:
                print(json.dumps({
                    "id": msg.get("id"),
                    "from": msg.get("from"),
                    "subject": msg.get("subject"),
                    "preview": msg.get("preview", "")[:200],
                    "unread": msg.get("unread", False)
                }, ensure_ascii=False))

            # 更新 last_seen
            last_seen = new_messages[0]["id"]  # ULID 时间有序，取最新的
            print(f"LAST_SEEN={last_seen}")
            sys.exit(0)

        # 等待下一轮
        time.sleep(interval)


if __name__ == "__main__":
    main()
