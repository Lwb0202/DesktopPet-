"""桌面痕迹系统。

用户长时间空闲时，宠物在桌面留下"生活痕迹"——脚印、Zzz、涂鸦等。
每个痕迹为独立透明窗口，自动淡入淡出，不修改真实桌面文件。

集成方式：在 main.py 中创建 DeskMarkManager 并调用 start()。
"""

import random
import math
import logging
from enum import Enum
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QPropertyAnimation, QEasingCurve,
    pyqtSignal, QObject,
)
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QBrush, QPen, QFont,
)
from PyQt6.QtWidgets import (
    QWidget, QGraphicsOpacityEffect,
)
from event_system import get_idle_seconds

_log = logging.getLogger("marks")


# ═══════════════════════════════════════════════════════════════
#  配置（集中管理）
# ═══════════════════════════════════════════════════════════════

class MarksConfig:
    IDLE_MINUTES = 30           # 空闲多久触发痕迹
    CHECK_INTERVAL_MS = 15_000  # 空闲检测间隔（15s）
    MAX_MARKS = 5               # 同时最多痕迹数
    SPAWN_CHANCE = 0.40         # 每次检测时生成痕迹的概率
    LIFETIME_SEC = 600          # 痕迹存活时间（10分钟）
    FADE_IN_MS = 2000           # 淡入动画时长
    FADE_OUT_MS = 3000          # 淡出动画时长
    MIN_SIZE = 48               # 痕迹最小尺寸
    MAX_SIZE = 72               # 痕迹最大尺寸
    EDGE_MARGIN = 40            # 距屏幕边缘的最小距离


# ═══════════════════════════════════════════════════════════════
#  痕迹类型
# ═══════════════════════════════════════════════════════════════

class MarkType(Enum):
    PAW = "paw"                 # 小脚印
    SLEEP_BUBBLE = "sleep"      # 睡觉气泡
    DOODLE_STAR = "star"        # 小星星涂鸦
    DOODLE_HEART = "heart"      # 小爱心涂鸦
    ZZZ = "zzz"                 # Zzz 文字

    @classmethod
    def random(cls):
        return random.choice(list(cls))


# ═══════════════════════════════════════════════════════════════
#  DeskMark — 单个痕迹窗口
# ═══════════════════════════════════════════════════════════════

class DeskMark(QWidget):
    """单个桌面痕迹。无边框、透明、无交互、自动淡入淡出。"""

    fade_done = pyqtSignal(object)  # 淡出完成后发射自身引用

    # ── 调色板 ──
    _COLORS = {
        MarkType.PAW:           QColor(180, 140, 110, 120),
        MarkType.SLEEP_BUBBLE:  QColor(200, 190, 220, 90),
        MarkType.DOODLE_STAR:   QColor(220, 190, 130, 100),
        MarkType.DOODLE_HEART:  QColor(210, 150, 150, 100),
        MarkType.ZZZ:           QColor(160, 170, 210, 110),
    }

    _DRAW_COLORS = {
        MarkType.PAW:           QColor(160, 120, 90, 140),
        MarkType.SLEEP_BUBBLE:  QColor(140, 130, 170, 120),
        MarkType.DOODLE_STAR:   QColor(190, 160, 100, 130),
        MarkType.DOODLE_HEART:  QColor(180, 120, 120, 130),
        MarkType.ZZZ:           QColor(130, 140, 180, 140),
    }

    def __init__(self, mark_type: MarkType, position: QPoint, size: int):
        super().__init__()
        self._type = mark_type
        self._size = size
        self._angle = random.uniform(-25, 25)  # 随机旋转

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(size, size)
        self.move(position)

        # 透明度效果
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self.show()

    # ── 动画控制 ──────────────────────────────────────────────

    def fade_in(self, on_done=None):
        """淡入。"""
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(MarksConfig.FADE_IN_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if on_done:
            anim.finished.connect(on_done)
        anim.start()
        return anim

    def fade_out(self):
        """淡出，完成后发射 fade_done。"""
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(MarksConfig.FADE_OUT_MS)
        anim.setStartValue(self._opacity.opacity())
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(lambda: self.fade_done.emit(self))
        anim.start()
        return anim

    # ── 绘制 ──────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self._size // 2, self._size // 2)
        p.rotate(self._angle)

        draw_fn = {
            MarkType.PAW:           self._draw_paw,
            MarkType.SLEEP_BUBBLE:  self._draw_sleep_bubble,
            MarkType.DOODLE_STAR:   self._draw_star,
            MarkType.DOODLE_HEART:  self._draw_heart,
            MarkType.ZZZ:           self._draw_zzz,
        }
        fn = draw_fn.get(self._type, self._draw_zzz)
        fn(p)
        p.end()

    def _draw_paw(self, p: QPainter):
        s = self._size
        r = s * 0.40
        cx, cy = 0, int(s * 0.08)
        color = self._DRAW_COLORS[MarkType.PAW]

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))

        # 主肉垫
        p.drawEllipse(QPoint(cx, cy + int(r * 0.35)), int(r * 0.6), int(r * 0.45))

        # 四个小脚趾
        pr = int(r * 0.22)
        offsets = [(-0.32, -0.25), (-0.12, -0.38), (0.12, -0.38), (0.32, -0.25)]
        for dx, dy in offsets:
            px = cx + int(r * dx)
            py = cy + int(r * dy)
            p.drawEllipse(QPoint(px, py), pr, int(pr * 0.85))

    def _draw_sleep_bubble(self, p: QPainter):
        s = self._size
        color = self._DRAW_COLORS[MarkType.SLEEP_BUBBLE]

        # 圆角气泡底
        p.setPen(Qt.PenStyle.NoPen)
        bg = QColor(color.red(), color.green(), color.blue(), 60)
        p.setBrush(QBrush(bg))
        bubble_rect = QRect(-s // 3, -s // 4, s * 2 // 3, s // 2)
        p.drawRoundedRect(bubble_rect, 16, 16)

        # Zzz 文字
        p.setPen(QPen(color, 2))
        font = QFont("Arial", int(s * 0.28), QFont.Weight.Bold)
        font.setItalic(True)
        p.setFont(font)
        p.drawText(bubble_rect, Qt.AlignmentFlag.AlignCenter, "Zzz")

    def _draw_star(self, p: QPainter):
        s = self._size
        color = self._DRAW_COLORS[MarkType.DOODLE_STAR]
        r = s * 0.38

        path = QPainterPath()
        for i in range(5):
            angle = math.radians(-90 + i * 72)
            outer_x = r * math.cos(angle)
            outer_y = r * math.sin(angle)
            inner_angle = math.radians(-90 + i * 72 + 36)
            inner_r = r * 0.38
            inner_x = inner_r * math.cos(inner_angle)
            inner_y = inner_r * math.sin(inner_angle)

            if i == 0:
                path.moveTo(outer_x, outer_y)
            else:
                path.lineTo(outer_x, outer_y)
            path.lineTo(inner_x, inner_y)
        path.closeSubpath()

        p.setPen(QPen(color.darker(120), 1.5))
        p.setBrush(QBrush(color))
        p.drawPath(path)

    def _draw_heart(self, p: QPainter):
        s = self._size
        color = self._DRAW_COLORS[MarkType.DOODLE_HEART]
        r = s * 0.30

        path = QPainterPath()
        path.moveTo(0, r * 0.9)
        # 右半弧
        path.cubicTo(0, r * 0.2, r * 0.7, -r * 0.5, 0, -r * 0.9)
        # 左半弧
        path.cubicTo(-r * 0.7, -r * 0.5, 0, r * 0.2, 0, r * 0.9)

        p.setPen(QPen(color.darker(120), 1.5))
        p.setBrush(QBrush(color))
        p.drawPath(path)

    def _draw_zzz(self, p: QPainter):
        s = self._size
        color = self._DRAW_COLORS[MarkType.ZZZ]

        p.setPen(QPen(color, 2))
        font = QFont("Arial", int(s * 0.42), QFont.Weight.Bold)
        font.setItalic(True)
        p.setFont(font)

        texts = ["Z", "z", "Z"]
        offsets = [(-s // 5, -s // 3), (0, 0), (s // 5, s // 3)]
        for i, (dx, dy) in enumerate(offsets):
            c = QColor(color.red(), color.green(), color.blue(),
                       int(color.alpha() * (1.0 - i * 0.25)))
            p.setPen(QPen(c, 2))
            p.drawText(QRect(dx - s // 3, dy - s // 4, s * 2 // 3, s // 2),
                       Qt.AlignmentFlag.AlignCenter, texts[i])


# ═══════════════════════════════════════════════════════════════
#  DeskMarkManager — 痕迹生命周期管理
# ═══════════════════════════════════════════════════════════════

class DeskMarkManager(QObject):
    """管理痕迹的生成、存活和清理。

    Usage::

        mgr = DeskMarkManager(pet)
        mgr.start()
    """

    def __init__(self, pet, config: MarksConfig | None = None):
        super().__init__()
        self._pet = pet
        self._cfg = config or MarksConfig()
        self._marks: list[DeskMark] = []

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.setInterval(self._cfg.CHECK_INTERVAL_MS)

    # ── 公开 API ──────────────────────────────────────────────

    def start(self):
        self._timer.start()
        _log.info(f"[痕迹系统] 已启动 (间隔: {self._cfg.CHECK_INTERVAL_MS // 1000}s, "
              f"空闲阈值: {self._cfg.IDLE_MINUTES}min)")

    def stop(self):
        self._timer.stop()
        for m in self._marks:
            m.hide()
            m.deleteLater()
        self._marks.clear()

    def clear_all(self):
        """立即清除所有痕迹（不停止定时器）。"""
        for m in self._marks:
            m.hide()
            m.deleteLater()
        self._marks.clear()

    def spawn_mark(self, position: QPoint | None = None,
                   mark_type: MarkType | None = None) -> DeskMark | None:
        """手动生成一个痕迹（供外部扩展使用）。"""
        if len(self._marks) >= self._cfg.MAX_MARKS:
            return None
        return self._create_mark(mark_type or MarkType.random(), position)

    @property
    def mark_count(self) -> int:
        return len(self._marks)

    # ── 内部 ──────────────────────────────────────────────────

    def _check(self):
        idle_min = get_idle_seconds() / 60.0

        if idle_min < self._cfg.IDLE_MINUTES:
            # 用户回来了 → 清除所有痕迹
            if self._marks:
                self.clear_all()
            return

        if len(self._marks) >= self._cfg.MAX_MARKS:
            return

        if random.random() > self._cfg.SPAWN_CHANCE:
            return

        self._create_mark()

    def _create_mark(self, mark_type: MarkType | None = None,
                     position: QPoint | None = None) -> DeskMark:
        if mark_type is None:
            mark_type = MarkType.random()

        size = random.randint(self._cfg.MIN_SIZE, self._cfg.MAX_SIZE)

        if position is None:
            position = self._random_position(size)

        mark = DeskMark(mark_type, position, size)
        mark.fade_done.connect(self._on_mark_faded)

        # 淡入
        mark.fade_in(
            on_done=lambda m=mark: self._schedule_fade_out(m)
        )

        self._marks.append(mark)
        _log.info(f"[痕迹] 生成 {mark_type.value} @ ({position.x()},{position.y()}) "
              f"({len(self._marks)}/{self._cfg.MAX_MARKS})")
        return mark

    def _schedule_fade_out(self, mark: DeskMark):
        """淡入完成后，安排存活时间结束后淡出。"""
        QTimer.singleShot(self._cfg.LIFETIME_SEC * 1000, mark.fade_out)

    def _on_mark_faded(self, mark: DeskMark):
        """淡出完成后清理。"""
        if mark in self._marks:
            self._marks.remove(mark)
        mark.deleteLater()

    def _random_position(self, size: int) -> QPoint:
        """在宠物所在屏幕上随机生成位置。"""
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.screenAt(self._pet.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        m = self._cfg.EDGE_MARGIN
        x = random.randint(geo.left() + m, max(geo.left() + m, geo.right() - size - m))
        y = random.randint(geo.top() + m, max(geo.top() + m, geo.bottom() - size - m))
        return QPoint(x, y)
