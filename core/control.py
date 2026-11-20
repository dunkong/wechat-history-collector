"""采集任务控制器：支持暂停/继续/停止。线程安全。"""
import threading


class TaskControl:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = False
        self._pause = False
        self._event = threading.Event()  # pause 时等待，resume/stop 时唤醒

    def pause(self):
        with self._lock:
            self._pause = True

    def resume(self):
        with self._lock:
            self._pause = False
        self._event.set()  # 唤醒等待中的线程

    def stop(self):
        with self._lock:
            self._stop = True
            self._pause = False
        self._event.set()  # 立即唤醒，避免暂停时停止卡住

    def is_stopped(self):
        with self._lock:
            return self._stop

    def is_paused(self):
        with self._lock:
            return self._pause

    def wait_if_paused(self):
        """若处于暂停状态则阻塞等待，直到 resume 或 stop。"""
        while True:
            with self._lock:
                if self._stop or not self._pause:
                    return
            self._event.wait(timeout=0.5)
            self._event.clear()

    def reset(self):
        with self._lock:
            self._stop = False
            self._pause = False
        self._event.set()
        self._event.clear()
