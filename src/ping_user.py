import os
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv()

def parse_args():
    p = argparse.ArgumentParser(description="Send a mention via Discord webhook with custom message.")
    p.add_argument("--webhook", default=os.getenv("DISCORD_WEBHOOK_URL"), help="Webhook URL (or set DISCORD_WEBHOOK_URL in .env)")
    p.add_argument("--user-id", type=str, default=os.getenv("TARGET_USER_ID"), help="Target user ID to mention (or set TARGET_USER_ID in .env)")
    p.add_argument("--message", type=str, default=None, help="Message content. If omitted, script will prompt.")
    p.add_argument("--file", type=str, default=None, help="Optional: path to file to attach")
    return p.parse_args()

def build_payload(user_id: str, message: str):
    content = f"<@{user_id}> {message}"
    payload = {
        "content": content,
        "allowed_mentions": {
            "parse": [],
            "users": [str(user_id)]
        }
    }
    return payload

def send_via_webhook(webhook_url: str, payload: dict, file_path: Path = None, timeout=30):
    if file_path:
        with file_path.open("rb") as f:
            files = {
                "file": (file_path.name, f, "application/octet-stream"),
                "payload_json": (None, json.dumps(payload), "application/json")
            }
            r = requests.post(webhook_url, files=files, timeout=timeout)
    else:
        r = requests.post(webhook_url, json=payload, timeout=timeout)
    return r

def main():
    args = parse_args()

    if not args.webhook:
        print("ERROR: webhook not set. Provide --webhook or set DISCORD_WEBHOOK_URL in .env")
        return
    if not args.user_id:
        print("ERROR: user id not set. Provide --user-id or set TARGET_USER_ID in .env")
        return

    if args.message:
        message = args.message
    else:
        try:
            message = input("Nhập nội dung muốn gửi: ").strip()
        except KeyboardInterrupt:
            print("\nBị hủy.")
            return
        if not message:
            print("Không có nội dung. Hủy.")
            return

    file_path = None
    if args.file:
        p = Path(args.file)
        if not p.exists() or not p.is_file():
            print(f"ERROR: file not found: {args.file}")
            return
        file_path = p

    payload = build_payload(args.user_id, message)
    print("Đang gửi...", end=" ", flush=True)
    try:
        resp = send_via_webhook(args.webhook, payload, file_path)
    except Exception as e:
        print("Lỗi khi gửi:", e)
        return

    if resp.status_code in (200, 201, 204):
        print("OK (status:", resp.status_code, ")")
    else:
        print("Thất bại (status:", resp.status_code, ")")
        try:
            print("Response:", resp.text)
        except Exception:
            pass

if __name__ == "__main__":
    main()
