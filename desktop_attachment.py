"""桌面窗口依附系统。

让桌宠与前台窗口产生物理互动：自动坐在窗口边缘、跟随窗口移动、
快速移动时滑落。不修改 PetWindow 状态机结构。

核心概念:
    GROUNDED — 宠物在桌面上，正常行为（持续检测窗口碰撞）
    ATTACHED — 宠物坐在窗口顶部边缘，跟随移动（lerp 惯性）
    FALLING  — 宠物正在下落，碰到窗口边缘则附着，落到底部则回到 GROUNDED
"""

import random
import ctypes
import logging
from ctypes import wintypes
from enum import Enum
from PyQt6.QtCore import (
    QObject, QTimer, QRect, QPoint, pyqtSignal,
)
from PyQt6.QtGui import QGuiApplication

_log = logging.getLogger("attach")


# ═══════════════════════════════════════════════════════════════
#  Win32 API
# ═══════════════════════════════════════════════════════════════

_user32 = ctypes.windll.user32
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL


def _foreground_hwnd() -> int:
    return _user32.GetForegroundWindow() or 0


def _window_rect(hwnd: int) -> QRect | None:
    if not hwnd:
        return None
    r = wintypes.RECT()
    if not _user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r)):
        return None
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    return QRect(r.left, r.top, w, h)


def _is_rect_on_screen(rect: QRect) -> bool:
    """检查矩形是否至少部分在某个屏幕内（排除最小化窗口的 -32000 坐标）。"""
    for screen in QGuiApplication.screens():
        sg = screen.geometry()
        if sg.intersects(rect):
            return True
    return False


# ═══════════════════════════════════════════════════════════════
#  配置（集中管理）
# ═══════════════════════════════════════════════════════════════

class AttachConfig:
    SNAP_RANGE_H = 140         # 水平吸附范围（px）
    SNAP_RANGE_V = 80          # 垂直吸附范围（px）
    FOLLOW_LERP = 0.25         # 跟随插值率（越小惯性越强）
    FALL_SPEED_MIN = 6         # 下落初速（px/tick）
    FALL_SPEED_MAX = 16        # 下落最大速度
    FALL_SPEED_ACCEL = 0.8     # 下落加速度
    SHAKE_THRESHOLD = 40       # 窗口位移阈值（px）
    SLIP_CHANCE = 0.35         # 滑落概率
    POLL_INTERVAL_MS = 40      # 主循环间隔
    MIN_WINDOW_WIDTH = 200     # 不吸附太窄的窗口
    DETACH_COOLDOWN_MS = 2000  # 脱离后多久才能重新吸附
    SETTLE_TICKS = 5           # 静止多少 tick 后才检测吸附
    WINDOW_JUMP_THRESHOLD = 300 # 窗口单帧位移超过此值视为"切换了窗口"→直接脱离


class _State(Enum):
    GROUNDED = "grounded"
    ATTACHED = "attached"
    FALLING = "falling"


class DesktopAttachment(QObject):

    attached = pyqtSignal(bool)

    def __init__(self, pet, config: AttachConfig | None = None):
        super().__init__()
        self._pet = pet
        self._cfg = config or AttachConfig()

        self._state = _State.GROUNDED
        self._win_rect: QRect | None = None
        self._win_prev_center = QPoint()
        self._fall_speed = 0.0
        self._last_pet_pos = pet.pos()
        self._settle_counter = 0
        self._detach_until = 0
        self._attached_hwnd = 0     # 吸附到哪个窗口

        self._tick_count = 0

    # ── 公开 API ──────────────────────────────────────────────

    def start(self):
        from tick_manager import TickManager
        TickManager.instance().register("attach", self._tick, self._cfg.POLL_INTERVAL_MS)
        _log.info(f"[依附系统] 已启动 (间隔: {self._cfg.POLL_INTERVAL_MS}ms)")

    def stop(self):
        from tick_manager import TickManager
        TickManager.instance().unregister("attach")
        if self._state == _State.ATTACHED:
            self._detach()

    def detach_if_attached(self):
        if self._state == _State.ATTACHED:
            self._start_falling()

    # ═══════════════════════════════════════════════════════════
    #  主循环
    # ═══════════════════════════════════════════════════════════

    def _tick(self):
        self._tick_count += 1
        fg_hwnd = _foreground_hwnd()
        win_rect = _window_rect(fg_hwnd)
        pet_geo = self._pet.frameGeometry()

        # 跟踪宠物是否在移动
        cur_pos = self._pet.pos()
        moved = (abs(cur_pos.x() - self._last_pet_pos.x()) > 1 or
                 abs(cur_pos.y() - self._last_pet_pos.y()) > 1)
        self._settle_counter = 0 if moved else self._settle_counter + 1
        self._last_pet_pos = cur_pos

        # 窗口位移
        win_center = win_rect.center() if win_rect else QPoint()
        win_delta = 0
        if win_rect and self._win_rect:
            win_delta = (abs(win_center.x() - self._win_prev_center.x()) +
                         abs(win_center.y() - self._win_prev_center.y()))

        if self._state == _State.ATTACHED:
            self._tick_attached(fg_hwnd, win_rect, win_delta, pet_geo)
        elif self._state == _State.FALLING:
            self._tick_falling(win_rect, pet_geo)
        else:
            self._tick_grounded(win_rect, pet_geo)

        self._win_rect = win_rect
        self._win_prev_center = win_center

    # ── ATTACHED ──────────────────────────────────────────────

    def _tick_attached(self, fg_hwnd, win_rect, win_delta, pet_geo):
        # ① 吸附的窗口被切换走了（Alt+Tab / 最小化）→ 下落
        if fg_hwnd != self._attached_hwnd:
            _log.info(f"[依附] 窗口已切换 → 脱离")
            self._start_falling()
            return

        # ② 窗口消失了 → 下落
        if win_rect is None:
            self._start_falling()
            return

        # ③ 窗口被最小化（跑到屏幕外）→ 下落
        if not _is_rect_on_screen(win_rect):
            _log.info(f"[依附] 窗口最小化 → 脱离")
            self._start_falling()
            return

        # ④ 窗口突变（跳过大距离，可能是虚拟桌面切换等）→ 下落
        if win_delta >= self._cfg.WINDOW_JUMP_THRESHOLD:
            _log.info(f"[依附] 窗口突变 ({win_delta}px) → 脱离")
            self._start_falling()
            return

        # ⑤ 窗口快速移动 → 概率滑落
        if win_delta >= self._cfg.SHAKE_THRESHOLD:
            if random.random() < self._cfg.SLIP_CHANCE:
                _log.info(f"[依附] 窗口抖动 ({win_delta}px) → 滑落")
                self._start_falling()
                return

        # ⑥ 正常跟随（lerp 惯性）
        target_x = win_rect.left()
        target_y = win_rect.top() - pet_geo.height() + 2
        cur = pet_geo.topLeft()
        lerp = self._cfg.FOLLOW_LERP
        new_x = cur.x() + (target_x - cur.x()) * lerp
        new_y = target_y

        # 钳制到屏幕范围内
        new_x, new_y = self._clamp_to_screen(int(new_x), int(new_y),
                                             pet_geo.width(), pet_geo.height())
        self._pet.move(new_x, new_y)

    # ── FALLING ───────────────────────────────────────────────

    def _tick_falling(self, win_rect, pet_geo):
        screen_bottom = self._screen_bottom()
        if pet_geo.bottom() >= screen_bottom:
            self._land()
            return

        self._fall_speed = min(
            self._fall_speed + self._cfg.FALL_SPEED_ACCEL,
            self._cfg.FALL_SPEED_MAX,
        )
        self._pet.move(pet_geo.x(), pet_geo.y() + int(self._fall_speed))

    # ── GROUNDED ──────────────────────────────────────────────

    def _tick_grounded(self, win_rect, pet_geo):
        if not win_rect or not self._is_valid_snap_target(win_rect):
            return
        if self._tick_count < self._detach_until:
            return
        if self._settle_counter < self._cfg.SETTLE_TICKS:
            return

        pet_bottom = pet_geo.bottom()
        pet_cx = pet_geo.center().x()

        # 宠物必须在窗口上方（允许少量重叠），防止从屏幕底部误吸
        if pet_bottom > win_rect.top() + 20:
            return

        if self._check_snap(win_rect, pet_cx, pet_bottom):
            self._attach_to(win_rect)

    # ═══════════════════════════════════════════════════════════
    #  状态转换
    # ═══════════════════════════════════════════════════════════

    def _attach_to(self, win_rect: QRect):
        self._state = _State.ATTACHED
        self._attached_hwnd = _foreground_hwnd()
        self._fall_speed = 0.0
        self._pet.sit_still()
        target_y = win_rect.top() - self._pet.height() + 2
        target_x = win_rect.left()
        target_x, target_y = self._clamp_to_screen(
            target_x, target_y, self._pet.width(), self._pet.height()
        )
        self._pet.move(target_x, target_y)
        self.attached.emit(True)
        _log.info(f"[依附] 吸附到窗口 hwnd={self._attached_hwnd:#x} "
              f"({win_rect.left()},{win_rect.top()})")

    def _start_falling(self):
        self._state = _State.FALLING
        self._attached_hwnd = 0
        self._fall_speed = random.uniform(
            self._cfg.FALL_SPEED_MIN, self._cfg.FALL_SPEED_MIN + 3
        )
        self._detach_until = self._tick_count + int(
            self._cfg.DETACH_COOLDOWN_MS / self._cfg.POLL_INTERVAL_MS
        )
        self.attached.emit(False)
        _log.info(f"[依附] 开始下落 v={self._fall_speed:.1f}")

    def _detach(self):
        self._state = _State.GROUNDED
        self._attached_hwnd = 0
        self._fall_speed = 0.0
        self.attached.emit(False)

    def _land(self):
        self._state = _State.GROUNDED
        self._attached_hwnd = 0
        self._fall_speed = 0.0
        self.attached.emit(False)
        # 落地后延长冷却，防止立即重新吸附造成震荡
        self._detach_until = self._tick_count + int(
            self._cfg.DETACH_COOLDOWN_MS * 3 / self._cfg.POLL_INTERVAL_MS
        )
        _log.info("[依附] 落地")

    # ═══════════════════════════════════════════════════════════
    #  碰撞 / 验证
    # ═══════════════════════════════════════════════════════════

    def _check_snap(self, win_rect: QRect, pet_cx: int, pet_bottom: int) -> bool:
        vert_ok = abs(pet_bottom - win_rect.top()) <= self._cfg.SNAP_RANGE_V
        horiz_ok = (win_rect.left() - self._cfg.SNAP_RANGE_H
                    <= pet_cx
                    <= win_rect.right() + self._cfg.SNAP_RANGE_H)
        return vert_ok and horiz_ok

    def _is_valid_snap_target(self, wr: QRect) -> bool:
        if wr is None:
            return False
        if wr.width() < self._cfg.MIN_WINDOW_WIDTH:
            return False
        if not _is_rect_on_screen(wr):
            return False
        return True

    def _screen_bottom(self) -> int:
        screen = QGuiApplication.screenAt(self._pet.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry().bottom()

    def _clamp_to_screen(self, x: int, y: int, pw: int, ph: int):
        """确保宠物不跑到屏幕外。"""
        screen = QGuiApplication.screenAt(QPoint(x, y))
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = max(geo.left(), min(geo.right() - pw, x))
        y = max(geo.top(), min(geo.bottom() - ph, y))
        return x, y
