"""统一 Tick 分发器。

合并高频 QTimer，单一 16ms 定时器分发给所有注册的回调。
支持全局暂停（全屏游戏/锁屏时自动冻结所有动画）。
"""

import time
import logging
from PyQt6.QtCore import QTimer

_log = logging.getLogger("tick")


class TickManager:
    """单例 Tick 分发器。

    用法:
        tm = TickManager.instance()
        tm.register("anim", callback, interval_ms=16)
        tm.pause_all()   # 全屏游戏时冻结
        tm.resume_all()
    """

    _instance: "TickManager | None" = None

    def __init__(self):
        self._callbacks: dict[str, tuple] = {}  # name → (fn, interval_ms, last_ms)
        self._paused = False
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(16)
        self._timer.start()
        self._tick_count = 0
        _log.info("TickManager 已启动 (16ms)")

    @classmethod
    def instance(cls) -> "TickManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 注册/注销 ──────────────────────────────────────────────

    def register(self, name: str, callback, interval_ms: int = 16):
        """注册一个回调。interval_ms 为调用间隔。"""
        self._callbacks[name] = (callback, max(1, interval_ms), 0)
        _log.debug(f"注册 tick: {name} ({interval_ms}ms)")

    def unregister(self, name: str):
        self._callbacks.pop(name, None)

    # ── 暂停/恢复 ──────────────────────────────────────────────

    def pause_all(self):
        if not self._paused:
            self._paused = True
            _log.info("全部 tick 已暂停")

    def resume_all(self):
        if self._paused:
            self._paused = False
            # 重置累积时间，避免恢复后瞬间大量回调
            for name in self._callbacks:
                self._callbacks[name] = (*self._callbacks[name][:2], 0)
            _log.info("全部 tick 已恢复")

    # ── 主循环 ─────────────────────────────────────────────────

    def _tick(self):
        if self._paused:
            return
        self._tick_count += 1
        now_ms = time.perf_counter_ns() // 1_000_000

        for name in list(self._callbacks):
            fn, interval, last = self._callbacks[name]
            if now_ms - last >= interval:
                try:
                    fn()
                except Exception:
                    _log.exception(f"Tick 回调异常: {name}")
                after_ms = time.perf_counter_ns() // 1_000_000
                elapsed = after_ms - now_ms
                if elapsed > max(interval, 100):
                    _log.warning(f"Tick 回调耗时过长: {name} ({elapsed}ms, 间隔{interval}ms)")
                # 在回调完成后才更新 last，防止慢回调导致堆积
                self._callbacks[name] = (fn, interval, after_ms)
