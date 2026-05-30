"""主动事件系统 —— 基于条件触发宠物行为。

纯 QTimer 驱动，不修改 PetWindow 状态机。
检测三类事件：连续工作、深夜、空闲。
"""

import ctypes
import random
import logging
from ctypes import wintypes
from datetime import datetime
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

_log = logging.getLogger("event")


# ═══════════════════════════════════════════════════════════════
#  阈值配置（集中管理）
# ═══════════════════════════════════════════════════════════════

class EventConfig:
    WORK_MINUTES = 90          # 连续工作多久触发提醒（分钟）
    NIGHT_HOUR = 23            # 几点进入深夜模式
    MORNING_HOUR = 6           # 几点退出深夜模式
    IDLE_MINUTES = 30          # 多久无操作触发闲逛（分钟）
    CHECK_INTERVAL_MS = 30_000 # 条件检查间隔（毫秒）
    BREAK_THRESHOLD_MIN = 5    # 空闲多久算"休息"（分钟），休息后重置工作计时
    WORK_REMIND_COOLDOWN = 60  # 工作提醒冷却时间（分钟），避免反复骚扰


# ═══════════════════════════════════════════════════════════════
#  工作提醒气泡池
# ═══════════════════════════════════════════════════════════════

WORK_REMINDERS = [
    "你已经连续工作很久了，起来喝杯水吧~",
    "眼睛该休息一下啦，看看窗外！",
    "肩膀酸不酸？起来活动活动~",
    "已经工作很久了哦，休息一下吧！",
    "该摸鱼了！劳逸结合才有效率~",
    "起来走走吧，久坐对身体不好~",
    "已连续工作 90 分钟，该歇歇了！",
    "盯屏幕太久会近视的，休息一下嘛~",
    "我替你数了，该休息了！",
    "喝口水，伸个懒腰，再回来继续~",
]

NIGHT_REMINDERS = [
    "都这么晚了，该睡觉了...",
    "熬夜会掉头发的！",
    "晚安时间到~",
    "好困...你还不睡吗？",
    "已经深夜了，明天再继续吧~",
    "再不睡觉明天会变熊猫的！",
]

IDLE_BUBBLES = [
    "好无聊呀...你还在吗？",
    "？没人理我了吗",
    "我自己溜达溜达~",
    "...你在干嘛呢？",
    "喵？好像没人了...",
]


# ═══════════════════════════════════════════════════════════════
#  Windows 空闲检测（纯 ctypes）
# ═══════════════════════════════════════════════════════════════

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


def get_idle_seconds() -> float:
    """获取自上次用户输入（鼠标/键盘）以来的秒数。"""
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    tick = ctypes.windll.kernel32.GetTickCount()
    return (tick - lii.dwTime) / 1000.0


# ═══════════════════════════════════════════════════════════════
#  EventSystem
# ═══════════════════════════════════════════════════════════════

class EventSystem(QObject):
    """条件驱动的主动事件引擎。

    Usage::

        events = EventSystem(pet, memory)
        events.start()
    """

    # 信号：供外部监听（可选）
    work_reminder_triggered = pyqtSignal(int)   # 累计工作分钟
    night_mode_changed = pyqtSignal(bool)        # True=进入深夜, False=退出
    idle_wander_triggered = pyqtSignal(float)    # 空闲秒数

    def __init__(self, pet, memory, config: EventConfig | None = None):
        super().__init__()
        self._pet = pet
        self._memory = memory
        self._cfg = config or EventConfig()

        # ── 内部状态 ──
        self._work_start: float | None = None    # 本次工作起始 tick（秒）
        self._work_seconds = 0                    # 累计工作秒数
        self._last_remind_time: float | None = None
        self._night_active = False
        self._was_idle = False
        self._night_bubbles_shown = 0

        # ── 主定时器 ──
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(self._cfg.CHECK_INTERVAL_MS)

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self):
        """开始监控。应在 UI 就绪后调用。"""
        self._work_start = self._now_sec()
        self._timer.start()
        _log.info(f"[事件系统] 已启动 (检查间隔: {self._cfg.CHECK_INTERVAL_MS // 1000}s)")

    def stop(self):
        self._timer.stop()

    def touch(self):
        """通知事件系统：用户有活动（窗口切换等），重置空闲检测。"""
        self._was_idle = False

    # ── 核心 tick ─────────────────────────────────────────────

    def _tick(self):
        now = datetime.now()
        idle_sec = get_idle_seconds()

        # ── 1. 连续工作检测 ──
        self._check_work(now, idle_sec)

        # ── 2. 深夜检测 ──
        self._check_night(now)

        # ── 3. 空闲检测 ──
        self._check_idle(now, idle_sec)

    # ── 连续工作 ──────────────────────────────────────────────

    def _check_work(self, now, idle_sec):
        idle_min = idle_sec / 60.0

        # 用户长时间空闲 → 认为在休息，重置工作计时
        if idle_min >= self._cfg.BREAK_THRESHOLD_MIN:
            self._work_seconds = 0
            self._work_start = None
            return

        # 用户活跃中 → 累积工作秒数
        if self._work_start is None:
            self._work_start = self._now_sec()
        else:
            elapsed = self._now_sec() - self._work_start
            self._work_seconds += elapsed
            self._work_start = self._now_sec()

        work_min = self._work_seconds / 60.0
        if work_min >= self._cfg.WORK_MINUTES:
            self._fire_work_reminder(work_min)

    def _fire_work_reminder(self, work_min):
        # 冷却检查
        now_sec = self._now_sec()
        if self._last_remind_time is not None:
            if now_sec - self._last_remind_time < self._cfg.WORK_REMIND_COOLDOWN * 60:
                return

        self._last_remind_time = now_sec
        text = random.choice(WORK_REMINDERS)
        self._pet.show_bubble(text)
        self._work_seconds = 0  # 提醒后重置计时
        self.work_reminder_triggered.emit(int(work_min))
        _log.info(f"[事件] 工作提醒: {text}")

    # ── 深夜模式 ──────────────────────────────────────────────

    def _check_night(self, now):
        hour = now.hour
        is_night = (hour >= self._cfg.NIGHT_HOUR or hour < self._cfg.MORNING_HOUR)

        if is_night and not self._night_active:
            self._night_active = True
            self._enter_night_mode()
        elif not is_night and self._night_active:
            self._night_active = False
            self._exit_night_mode()

        # 深夜中偶尔提醒
        if self._night_active and self._night_bubbles_shown < 3:
            self._night_bubbles_shown += 1
            text = random.choice(NIGHT_REMINDERS)
            self._pet.show_bubble(text)

    def _enter_night_mode(self):
        self._pet.set_sleepy(True)
        self.night_mode_changed.emit(True)
        _log.info("[事件] 进入深夜模式")

    def _exit_night_mode(self):
        self._pet.set_sleepy(False)
        self._night_bubbles_shown = 0
        self.night_mode_changed.emit(False)
        _log.info("[事件] 退出深夜模式")

    # ── 空闲闲逛 ──────────────────────────────────────────────

    def _check_idle(self, now, idle_sec):
        idle_min = idle_sec / 60.0

        if idle_min >= self._cfg.IDLE_MINUTES and not self._was_idle:
            self._was_idle = True
            self._fire_idle_wander(idle_sec)
        elif idle_min < 1.0:
            self._was_idle = False

    def _fire_idle_wander(self, idle_sec):
        text = random.choice(IDLE_BUBBLES)
        self._pet.show_bubble(text)
        self._pet.start_wander()
        self.idle_wander_triggered.emit(idle_sec)
        _log.info(f"[事件] 空闲闲逛 ({idle_sec // 60:.0f}分钟无操作): {text}")

    # ── 工具 ──────────────────────────────────────────────────

    @staticmethod
    def _now_sec() -> float:
        return ctypes.windll.kernel32.GetTickCount() / 1000.0
