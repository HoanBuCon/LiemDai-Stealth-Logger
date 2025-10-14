import os
import time
import logging
import socket
import shutil
from pathlib import Path
from threading import Event

import requests
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

load_dotenv()
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", "assets"))
SENT_DIR = ASSETS_DIR / "sent"
LOG_FILE = os.getenv("LOG_FILE", "send_assets_watcher.log")
POLL_SLEEP = float(os.getenv("POLL_SLEEP", "0.5"))  # used for waiting file completion
SEND_DELAY = float(os.getenv("SEND_DELAY", "1.0"))  # delay between sends to be polite

if not WEBHOOK_URL:
    raise SystemExit("Missing DISCORD_WEBHOOK_URL in .env")

ASSETS_DIR.mkdir(parents=True, exist_ok=True)
SENT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()]
)
log = logging.getLogger("send_img_watcher")

stop_event = Event()

def get_public_ip(timeout=4):
    services = ["https://api.ipify.org?format=json", "https://ifconfig.co/json", "https://ipinfo.io/json"]
    for url in services:
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict):
                    for k in ("ip", "query"):
                        if k in j:
                            return str(j[k])
                # fallback to first string occurrence
                if "ip" in j:
                    return str(j["ip"])
        except Exception as e:
            log.debug("Public IP lookup failed (%s): %s", url, e)
    return "unknown"

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        log.debug("Local IP lookup failed: %s", e)
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "unknown"

def wait_for_file_ready(path: Path, timeout=20.0, poll=POLL_SLEEP):
    deadline = time.time() + timeout
    last_size = -1
    while time.time() < deadline:
        if not path.exists():
            time.sleep(poll)
            continue
        try:
            size = path.stat().st_size
        except Exception:
            size = -1
        if size > 0 and size == last_size:
            time.sleep(poll)
            return True
        last_size = size
        time.sleep(poll)
    return False

def send_file(filepath: Path, public_ip: str, local_ip: str, max_retries=2):
    attempt = 0
    while attempt <= max_retries and not stop_event.is_set():
        attempt += 1
        try:
            with open(filepath, "rb") as f:
                content = (f"Tệp tin: `{filepath.name}`\n"
                           f"Source public IP: `{public_ip}`\n"
                           f"Local IP: `{local_ip}`")
                files = {"file": (filepath.name, f)}
                resp = requests.post(WEBHOOK_URL, data={"content": content}, files=files, timeout=30)
            status = resp.status_code
            if status in (200, 201, 204):
                log.info("Sent %s (status=%s)", filepath.name, status)
                return True, status, resp.text
            else:
                log.warning("Send attempt %d failed for %s: status=%s text=%s", attempt, filepath.name, status, resp.text)
        except Exception as e:
            log.exception("Exception on send attempt %d for %s: %s", attempt, filepath.name, e)
        if attempt <= max_retries:
            time.sleep(1 + attempt)
    return False, None, "max retries exceeded"

class AssetCreatedHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        log.info("Detected new file: %s", path)
        ok = wait_for_file_ready(path, timeout=60)
        if not ok:
            log.warning("File %s not ready (timeout). Skipping.", path)
            return
        public_ip = get_public_ip()
        local_ip = get_local_ip()
        ok_send, status, resp_text = send_file(path, public_ip, local_ip)
        if ok_send:
            try:
                dest = SENT_DIR / path.name
                shutil.move(str(path), str(dest))
                log.info("Moved %s -> %s", path.name, dest)
            except Exception:
                log.exception("Could not move sent file %s", path.name)
        else:
            log.warning("Failed to send %s; leaving it in place for retry or manual inspection.", path.name)

def run_watcher():
    log.info("Starting assets watcher on %s", ASSETS_DIR)
    public_ip = get_public_ip()
    local_ip = get_local_ip()
    existing = [p for p in ASSETS_DIR.iterdir() if p.is_file()]
    if existing:
        log.info("Found %d existing files to send on startup.", len(existing))
    for p in existing:
        if stop_event.is_set(): break
        if not wait_for_file_ready(p, timeout=5):
            log.warning("Startup file %s not ready; skipping.", p)
            continue
        ok_send, status, _ = send_file(p, public_ip, local_ip)
        if ok_send:
            try:
                shutil.move(str(p), str(SENT_DIR / p.name))
            except Exception:
                log.exception("Could not move startup file %s", p.name)
        time.sleep(SEND_DELAY)

    observer = Observer()
    handler = AssetCreatedHandler()
    observer.schedule(handler, str(ASSETS_DIR), recursive=False)
    observer.start()
    try:
        while not stop_event.is_set():
            time.sleep(1.0)
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received, stopping watcher.")
    finally:
        observer.stop()
        observer.join()
        log.info("Watcher stopped.")

if __name__ == "__main__":
    run_watcher()
