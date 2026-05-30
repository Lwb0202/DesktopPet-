import math
import os
import random
import logging
from enum import Enum
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect, pyqtSignal

_log = logging.getLogger("pet")
from PyQt6.QtGui import (
    QMouseEvent, QPainter, QColor, QBrush,
    QPen, QPixmap, QGuiApplication,
)
from PyQt6.QtWidgets import QApplication, QWidget, QMenu, QLabel
from animation import AnimationController


# ═══════════════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════════════

class PetState(Enum):
    IDLE = "idle"
    SLEEP = "sleep"
    HAPPY = "happy"
    WANDER = "wander"
    STARE = "stare"
    CELEBRATE = "celebrate"    # 撒花
    DANCE = "dance"            # 跳舞
    JUMP_ROPE = "jump_rope"    # 跳绳
    HEAD_BALL = "head_ball"    # 顶足球
    CRY = "cry"                # 大哭
    SPIN = "spin"              # 转圈圈


TRANSITIONS: dict[PetState, list[tuple[PetState, float]]] = {
    PetState.IDLE: [
        (PetState.WANDER,    0.15),
        (PetState.STARE,     0.08),
        (PetState.SLEEP,     0.08),
        (PetState.HAPPY,     0.08),
        (PetState.DANCE,     0.10),
        (PetState.CELEBRATE, 0.08),
        (PetState.SPIN,      0.08),
        (PetState.JUMP_ROPE, 0.06),
        (PetState.HEAD_BALL, 0.06),
        (PetState.CRY,       0.05),
        (PetState.IDLE,      0.18),
    ],
    PetState.WANDER:    [(PetState.IDLE, 1.0)],
    PetState.STARE:     [(PetState.IDLE, 1.0)],
    PetState.SLEEP:     [(PetState.IDLE, 1.0)],
    PetState.HAPPY:     [(PetState.IDLE, 1.0)],
    PetState.CELEBRATE: [(PetState.IDLE, 1.0)],
    PetState.DANCE:     [(PetState.IDLE, 1.0)],
    PetState.JUMP_ROPE: [(PetState.IDLE, 1.0)],
    PetState.HEAD_BALL: [(PetState.IDLE, 1.0)],
    PetState.CRY:       [(PetState.IDLE, 1.0)],
    PetState.SPIN:      [(PetState.IDLE, 1.0)],
}

DURATIONS: dict[PetState, tuple[int, int]] = {
    PetState.IDLE:      (10, 25),
    PetState.WANDER:    (4, 10),
    PetState.STARE:     (5, 12),
    PetState.SLEEP:     (10, 25),
    PetState.HAPPY:     (3, 6),
    PetState.CELEBRATE: (4, 8),
    PetState.DANCE:     (5, 10),
    PetState.JUMP_ROPE: (4, 7),
    PetState.HEAD_BALL: (4, 8),
    PetState.CRY:       (5, 10),
    PetState.SPIN:      (3, 6),
}

WANDER_SPEED = 2.0
WANDER_TICK_MS = 33
EDGE_MARGIN = 30
CLICK_THRESHOLD = 5

BUBBLE_MESSAGES = [
    "你好呀~", "今天天气不错呢", "有点困...", "陪我玩嘛！",
    "不要点我 >_<", "喵~", "好无聊呀", "肚子饿了...",
    "加油！", "^^", "......", "哼！",
    "摸摸头~", "诶？", "嘻嘻", "我在思考喵生...",
    "别戳了！", "来玩嘛~",
]

BUBBLE_STYLE = """
    QLabel {
        background-color: #FFF8E7;
        color: #4A3728;
        border: 1.5px solid #E0D5C0;
        border-radius: 12px;
        padding: 6px 14px;
        font-size: 13px;
        font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    }
"""


# ═══════════════════════════════════════════════════════════════
#  PetWindow
# ═══════════════════════════════════════════════════════════════


def _paint_ghost(w: QWidget):
    """拖尾残影窗口的独立绘制函数。"""
    p = QPainter(w)
    pm = getattr(w, "_trail_pixmap", None)
    if pm and not pm.isNull():
        p.drawPixmap(0, 0, pm)
    p.end()


class PetWindow(QWidget):

    switch_requested = pyqtSignal()
    chat_requested = pyqtSignal()

    def __init__(self, pet_path: str | None = None):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setMouseTracking(True)

        # ── 动画控制器（分层系统）──
        self._ctrl = AnimationController(pet_path)
        self._last_tick_ns = 0

        # ── 核心状态 ──
        self._state = PetState.IDLE
        self._drag_offset = QPoint()
        self._press_pos: QPoint | None = None
        self._is_dragging = False

        # ── 闲逛 ──
        self._wander_target = QPoint()
        self._wander_active = False

        # ── 气泡 ──
        self._bubble: QLabel | None = None
        self._bubble_timer = QTimer(self)
        self._bubble_timer.timeout.connect(self._hide_bubble)
        self._bubble_timer.setSingleShot(True)

        # ── 事件系统 ──
        self._sleepy_bias = False
        self._emotion = None

        # ── 启动冻结 ──
        self._frozen = False

        # ── 双击检测 ──
        self._click_pending = False
        self._click_timer = QTimer(self)
        self._click_timer.timeout.connect(self._on_single_click)
        self._click_timer.setSingleShot(True)

        # 初始化视图
        self._apply_state_animation(PetState.IDLE)
        sz = self._ctrl.size
        self.setFixedSize(sz.width(), sz.height())

        # ── 拖尾残影 ──
        self._trail_ghosts: list[QWidget] = []
        self._trail_positions: list[QPoint] = []  # 环形缓冲
        self._trail_max = 4
        self._init_trails()

        from tick_manager import TickManager
        TickManager.instance().register("anim", self._on_anim_tick, 16)

        # 状态切换计时器
        self._switch_countdown = DURATIONS[PetState.IDLE][0]
        self._switch_timer = QTimer(self)
        self._switch_timer.timeout.connect(self._on_switch_tick)
        self._switch_timer.start(1000)

    # ═══════════════════════════════════════════════════════════
    #  动画更新
    # ═══════════════════════════════════════════════════════════

    def _on_anim_tick(self):
        import time
        now_ns = time.perf_counter_ns()
        dt_ms = ((now_ns - self._last_tick_ns) / 1_000_000) if self._last_tick_ns else 16
        self._last_tick_ns = now_ns
        self._ctrl.update(min(dt_ms, 50))  # cap to avoid spiral

        # 拖尾：闲逛时每帧记录位置，更新残影
        if self._state == PetState.WANDER:
            self._record_trail_frame()
        self._update_trails()

        self.update()

    # ═══════════════════════════════════════════════════════════
    #  状态机核心
    # ═══════════════════════════════════════════════════════════

    def _transition_to(self, new_state: PetState) -> None:
        if new_state == self._state:
            return
        self._exit_state(self._state)
        self._enter_state(new_state)

    def _enter_state(self, new_state: PetState) -> None:
        old = self._state
        self._state = new_state

        self._apply_state_animation(new_state)

        if new_state == PetState.WANDER:
            self._start_wander()
        elif new_state == PetState.IDLE and old == PetState.WANDER:
            self._stop_wander()

        lo, hi = DURATIONS.get(new_state, (10, 25))
        self._switch_countdown = random.randint(lo, hi)

    def _exit_state(self, old_state: PetState) -> None:
        if old_state == PetState.WANDER:
            self._stop_wander()
            self._trail_positions.clear()

    def _apply_state_animation(self, state: PetState) -> None:
        """将 PetState 映射为分层动画指令。"""
        # 先关掉所有 overlay
        for ov_name in ("heart", "zzz", "dots", "flower", "tear", "ball"):
            self._ctrl.set_overlay(ov_name, False)

        # ── Base ──
        base_map = {
            PetState.SLEEP:     "sleep",
            PetState.DANCE:     "dance",
            PetState.JUMP_ROPE: "jump_rope",
            PetState.SPIN:      "spin",
        }
        self._ctrl.set_base(base_map.get(state, "idle"))

        # ── Expression ──
        expr_map = {
            PetState.HAPPY:     "happy",
            PetState.CELEBRATE: "happy",
            PetState.CRY:       "sad",
            PetState.STARE:     "sleepy",
        }
        self._ctrl.set_expression(expr_map.get(state))

        # ── Overlay ──
        overlay_map = {
            PetState.HAPPY:     "heart",
            PetState.CELEBRATE: "flower",
            PetState.CRY:       "tear",
            PetState.HEAD_BALL: "ball",
            PetState.SLEEP:     "zzz",
            PetState.STARE:     "dots",
        }
        ov = overlay_map.get(state)
        if ov:
            self._ctrl.set_overlay(ov, True)

        # 情绪叠加（不覆盖已有 expression 的状态）
        if self._emotion is not None and state not in (
            PetState.SLEEP, PetState.HAPPY, PetState.CELEBRATE,
            PetState.CRY, PetState.STARE,
        ):
            em = self._emotion.current
            from ai.emotion_state import Emotion
            if em == Emotion.HAPPY:
                self._ctrl.set_expression("happy")
            elif em == Emotion.SAD:
                self._ctrl.set_expression("sad")

        sz = self._ctrl.size
        self.setFixedSize(sz.width(), sz.height())

    # ═══════════════════════════════════════════════════════════
    #  状态切换计时
    # ═══════════════════════════════════════════════════════════

    def _pick_next_state(self) -> PetState:
        entries = list(TRANSITIONS.get(self._state, [(PetState.IDLE, 1.0)]))
        if self._frozen:
            entries = [(st, w) for st, w in entries if st != PetState.WANDER]

        if self._sleepy_bias and self._state == PetState.IDLE:
            entries = [
                (st, w * (3.0 if st == PetState.SLEEP else 0.4 if st in (PetState.WANDER, PetState.HAPPY) else 1.0))
                for st, w in entries
            ]

        if self._emotion is not None and self._state == PetState.IDLE:
            mod = self._emotion.weight_modifier()
            entries = [
                (st, w * mod.get(st.name, 1.0))
                for st, w in entries
            ]

        states, weights = zip(*entries)
        return random.choices(states, weights=weights)[0]

    def _on_switch_tick(self) -> None:
        if self._state == PetState.WANDER and self._wander_active:
            return
        self._switch_countdown -= 1
        if self._switch_countdown <= 0:
            self._transition_to(self._pick_next_state())

    # ═══════════════════════════════════════════════════════════
    #  闲逛
    # ═══════════════════════════════════════════════════════════

    def _start_wander(self) -> None:
        if self._frozen:
            return
        bounds = self._screen_bounds()
        if bounds.width() <= 0 or bounds.height() <= 0:
            self._transition_to(PetState.IDLE)
            return
        tx = random.randint(bounds.left(), bounds.right())
        ty = random.randint(bounds.top(), bounds.bottom())
        self._wander_target = QPoint(tx, ty)
        self._wander_active = True
        from tick_manager import TickManager
        TickManager.instance().register("wander", self._wander_tick, WANDER_TICK_MS)

    def _stop_wander(self) -> None:
        self._wander_active = False
        from tick_manager import TickManager
        TickManager.instance().unregister("wander")

    def _wander_tick(self) -> None:
        pos = self.pos()
        dx = self._wander_target.x() - pos.x()
        dy = self._wander_target.y() - pos.y()
        dist = math.hypot(dx, dy)

        if dist < 6:
            self._transition_to(PetState.IDLE)
            return

        step_x = dx / dist * WANDER_SPEED
        step_y = dy / dist * WANDER_SPEED
        new_x = pos.x() + step_x
        new_y = pos.y() + step_y

        bounds = self._screen_bounds()
        new_x = max(bounds.left(), min(bounds.right(), new_x))
        new_y = max(bounds.top(), min(bounds.bottom(), new_y))

        self.move(int(new_x), int(new_y))

    def _screen_bounds(self) -> QRect:
        screen = QGuiApplication.screenAt(self.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        return QRect(
            geo.left() + EDGE_MARGIN,
            geo.top() + EDGE_MARGIN,
            max(0, geo.width() - self.width() - EDGE_MARGIN * 2),
            max(0, geo.height() - self.height() - EDGE_MARGIN * 2),
        )

    # ═══════════════════════════════════════════════════════════
    #  气泡文字
    # ═══════════════════════════════════════════════════════════

    def show_bubble(self, text: str | None = None) -> None:
        if self._bubble is None:
            self._bubble = QLabel(self)
            self._bubble.setStyleSheet(BUBBLE_STYLE)
            self._bubble.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self._bubble.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self._bubble.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        if text is None:
            if self._emotion is not None:
                text = self._emotion.pick_bubble(BUBBLE_MESSAGES)
            else:
                text = random.choice(BUBBLE_MESSAGES)
        self._bubble.setText(text)
        self._bubble.adjustSize()

        bubble_w = self._bubble.width()
        bubble_h = self._bubble.height()
        pet_global = self.mapToGlobal(QPoint(0, 0))
        bx = pet_global.x() + (self.width() - bubble_w) // 2
        by = pet_global.y() - bubble_h - 8
        self._bubble.move(bx, by)
        self._bubble.show()
        from tick_manager import TickManager
        TickManager.instance().register("bubble_follow", self._reposition_bubble, 50)
        self._bubble_timer.start(4000 if text else 2500)

    def _reposition_bubble(self) -> None:
        if self._bubble is None or not self._bubble.isVisible():
            from tick_manager import TickManager
            TickManager.instance().unregister("bubble_follow")
            return
        bw = self._bubble.width()
        bh = self._bubble.height()
        pet_global = self.mapToGlobal(QPoint(0, 0))
        bx = pet_global.x() + (self.width() - bw) // 2
        by = pet_global.y() - bh - 8
        self._bubble.move(bx, by)

    def _hide_bubble(self) -> None:
        from tick_manager import TickManager
        TickManager.instance().unregister("bubble_follow")
        if self._bubble is not None:
            self._bubble.hide()

    # ── 启动冻结 ──────────────────────────────────────────────

    def freeze(self) -> None:
        """冻结宠物：停止闲逛，但保留状态自动切换。"""
        if self._frozen:
            return
        self._frozen = True
        self._stop_wander()
        if self._state == PetState.WANDER:
            self._transition_to(PetState.IDLE)
        _log.info("已冻结")

    def unfreeze(self) -> None:
        """解冻：允许闲逛。"""
        if not self._frozen:
            return
        self._frozen = False
        _log.info("已解冻")

    # ── 事件系统公开 API ──────────────────────────────────────

    def set_sleepy(self, enabled: bool) -> None:
        self._sleepy_bias = enabled

    def set_emotion_manager(self, emotion) -> None:
        self._emotion = emotion
        # 情绪变更时刷新表达式层
        self._apply_state_animation(self._state)

    def sit_still(self) -> None:
        if self._state == PetState.WANDER:
            self._transition_to(PetState.IDLE)

    def start_wander(self) -> None:
        if self._state not in (PetState.WANDER, PetState.SLEEP):
            self._transition_to(PetState.WANDER)

    # ═══════════════════════════════════════════════════════════
    #  宠物热切换
    # ═══════════════════════════════════════════════════════════

    def switch_pet(self, pet_path: str | None) -> None:
        """热切换到另一个宠物。传入路径或 None（内置猫）。"""
        self._stop_wander()
        self._ctrl = AnimationController(pet_path)
        self._last_tick_ns = 0
        self._state = PetState.IDLE
        self._apply_state_animation(PetState.IDLE)
        sz = self._ctrl.size
        self.setFixedSize(sz.width(), sz.height())
        lo, hi = DURATIONS.get(PetState.IDLE, (10, 25))
        self._switch_countdown = random.randint(lo, hi)

    # ═══════════════════════════════════════════════════════════
    #  拖尾残影
    # ═══════════════════════════════════════════════════════════

    def _init_trails(self):
        """创建透明拖尾窗口（每个残影是一个独立的小窗口）。"""
        sz = self._ctrl.size
        for _ in range(self._trail_max):
            g = QWidget()
            g.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            g.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            g.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            g.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.WindowTransparentForInput
            )
            g.setFixedSize(sz.width(), sz.height())
            g._trail_pixmap = QPixmap()  # 存储要绘制的帧
            g.paintEvent = lambda e, w=g: _paint_ghost(w)
            g.hide()
            self._trail_ghosts.append(g)

    def _record_trail_frame(self):
        """在当前位置记录一帧（供拖尾回放）。"""
        frame = self._ctrl.composite()
        pm = frame.copy() if frame and not frame.isNull() else QPixmap()
        self._trail_positions.append((self.pos(), pm))
        if len(self._trail_positions) > self._trail_max * 3 + 1:
            self._trail_positions.pop(0)

    def _update_trails(self):
        """更新拖尾：每位残影从历史队列取位置和帧，设置窗口透明度。"""
        if (self._state != PetState.WANDER and not self._is_dragging) or len(self._trail_positions) < 2:
            for g in self._trail_ghosts:
                g.hide()
            return

        for i, g in enumerate(self._trail_ghosts):
            idx = (i + 1) * 3  # 每隔 3 帧取一个残影位置
            if idx < len(self._trail_positions):
                pos, pm = self._trail_positions[-(idx + 1)]
                g.move(pos)
                g._trail_pixmap = pm
                g.setWindowOpacity(max(0.04, 0.22 - i * 0.06))
                g.show()
                g.update()
            else:
                g.hide()


    # ═══════════════════════════════════════════════════════════
    #  绘制
    # ═══════════════════════════════════════════════════════════

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        pm = self._ctrl.composite()
        if pm and not pm.isNull():
            painter.drawPixmap(0, 0, pm)
        painter.end()

    # ═══════════════════════════════════════════════════════════
    #  鼠标交互
    # ═══════════════════════════════════════════════════════════

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self.frameGeometry().topLeft()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event and self._press_pos is not None:
            delta = event.globalPosition().toPoint() - self._press_pos
            if abs(delta.x()) > CLICK_THRESHOLD or abs(delta.y()) > CLICK_THRESHOLD:
                self._is_dragging = True
        if event and self._is_dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            # 拖动时也产生拖尾
            self._record_trail_frame()
            self._update_trails()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        was_dragging = self._is_dragging
        if event and event.button() == Qt.MouseButton.LeftButton:
            # 单击/双击检测（非拖动时）
            if not was_dragging and self._press_pos is not None:
                if self._click_pending:
                    self._click_timer.stop()
                    self._click_pending = False
                    self._on_double_click()
                else:
                    self._click_pending = True
                    self._click_timer.start(300)
            self._press_pos = None
            self._is_dragging = False
            # 拖尾清理
            self._trail_positions.clear()
            self._update_trails()
        super().mouseReleaseEvent(event)

    def _on_single_click(self) -> None:
        self._click_pending = False
        self.show_bubble()
        if self._emotion is not None:
            self._emotion.on_click()
        if self._state in (PetState.SLEEP, PetState.STARE, PetState.CRY,
                           PetState.CELEBRATE, PetState.SPIN):
            self._transition_to(PetState.IDLE)
        elif self._state == PetState.WANDER:
            self._transition_to(PetState.IDLE)

    def _on_double_click(self) -> None:
        self.chat_requested.emit()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        switch_action = menu.addAction("更换宠物...")
        switch_action.triggered.connect(self.switch_requested.emit)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.exec(event.globalPos())
