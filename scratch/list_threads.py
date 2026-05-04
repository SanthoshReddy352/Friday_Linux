import threading
import sys

def list_threads():
    print(f"Main Thread: {threading.main_thread().name}, Daemon: {threading.main_thread().daemon}")
    for t in threading.enumerate():
        print(f"Thread: {t.name}, Daemon: {t.daemon}, Alive: {t.is_alive()}")

if __name__ == "__main__":
    list_threads()
