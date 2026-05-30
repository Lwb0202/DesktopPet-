"""内置动画帧生成器。

当没有外部 PNG 资源时，用 QPainter 程序化生成默认猫咪的所有动画帧。
生成独立透明图层：base（身体）、expression（表情）、overlay（特效）。
"""

from __future__ import annotations
import math
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import (
    QPixmap, QPainter, QPainterPath, QColor, QBrush, QPen, QFont,
)
from .clip import AnimationClip


SIZE = 128
FPS_DEFAULT = 12

# ── 调色板 ──
C_BODY       = QColor(255, 180, 100)
C_EAR        = QColor(255, 160, 80)
C_FACE       = QColor(255, 210, 140)
C_NOSE       = QColor(255, 120, 120)
C_EYE        = QColor(50, 30, 20)
C_MOUTH      = QColor(80, 50, 30)
C_HIGHLIGHT  = QColor(255, 255, 255)
C_HEART      = QColor(255, 100, 130)
C_ZZZ        = QColor(100, 100, 180)
C_DOTS       = QColor(120, 120, 140)
C_TRANSPARENT = Qt.GlobalColor.transparent


# ═══════════════════════════════════════════════════════════════
#  Base Layer — 身体（含中性表情）
# ═══════════════════════════════════════════════════════════════

def _gen_base_idle(fps: int = FPS_DEFAULT, frames: int = 6) -> AnimationClip:
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = i / max(1, frames - 1) * math.pi * 2
        bounce = abs(math.sin(t)) * 6
        cy = int(SIZE * 0.55 + bounce)
        _draw_body(p, SIZE, cy)
        _draw_face(p, SIZE, cy, blink=(i >= 2), smile=0.3)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


def _gen_base_sleep(fps: int = 8, frames: int = 8) -> AnimationClip:
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = i / max(1, frames - 1) * math.pi * 2
        bounce = abs(math.sin(t * 0.5)) * 3
        cy = int(SIZE * 0.58 + bounce)
        _draw_body(p, SIZE, cy)
        _draw_face_sleep(p, SIZE, cy)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps, loop=True)


# ═══════════════════════════════════════════════════════════════
#  Expression Layer — 仅面部元素，背景透明
# ═══════════════════════════════════════════════════════════════

def _gen_expr_happy(fps: int = FPS_DEFAULT, frames: int = 6) -> AnimationClip:
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = i / max(1, frames - 1) * math.pi * 2
        bounce = abs(math.sin(t)) * 6
        cy = int(SIZE * 0.55 + bounce)
        _draw_face(p, SIZE, cy, blink=True, smile=0.6)
        # 腮红
        p.setPen(Qt.PenStyle.NoPen)
        blush = QColor(255, 150, 150, 80)
        p.setBrush(QBrush(blush))
        p.drawEllipse(QPoint(int(SIZE * 0.28), int(cy)), int(SIZE * 0.04), int(SIZE * 0.03))
        p.drawEllipse(QPoint(int(SIZE * 0.72), int(cy)), int(SIZE * 0.04), int(SIZE * 0.03))
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


def _gen_expr_sad(fps: int = 8, frames: int = 8) -> AnimationClip:
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = int(SIZE * 0.56)
        _draw_face(p, SIZE, cy, blink=True, smile=0.05)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


def _gen_expr_sleepy(fps: int = 8, frames: int = 8) -> AnimationClip:
    """半睁眼表情（仅眼睛部分，背景透明）。"""
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = int(SIZE * 0.56)
        eye_h = int(SIZE * 0.06 * 0.35)  # 半睁
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(C_EYE))
        for ex in [SIZE * 0.38, SIZE * 0.62]:
            p.drawEllipse(QPoint(int(ex), int(cy - 6)),
                          int(SIZE * 0.03), eye_h)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


# ═══════════════════════════════════════════════════════════════
#  Overlay Layer — 特效粒子，背景透明
# ═══════════════════════════════════════════════════════════════

def _gen_overlay_heart(fps: int = 10, frames: int = 10) -> AnimationClip:
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        t = i / max(1, frames - 1) * math.pi * 2
        for j in range(3):
            hx = int(SIZE * 0.22 + (i + j * 7) % 12 * SIZE * 0.05)
            hy = int(SIZE * 0.05 + math.sin(t + j) * 8)
            alpha = max(0, 200 - (i + j * 7) % 12 * 15)
            p.setBrush(QBrush(QColor(255, 100, 130, alpha)))
            p.drawEllipse(hx, hy, 6, 6)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


def _gen_overlay_zzz(fps: int = 8, frames: int = 8) -> AnimationClip:
    pixmaps: list[QPixmap] = []
    z_strs = [["z"], ["Z"], ["ZZ"], ["Z"]]
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(100, 100, 180, 150), 2))
        font = QFont("Arial", 14, QFont.Weight.Bold)
        font.setItalic(True)
        p.setFont(font)
        zi = (i * 2) % len(z_strs)
        p.drawText(QRect(int(SIZE * 0.50), int(SIZE * 0.02),
                          int(SIZE * 0.45), int(SIZE * 0.25)),
                   Qt.AlignmentFlag.AlignCenter, z_strs[zi][0])
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


def _gen_overlay_dots(fps: int = 6, frames: int = 6) -> AnimationClip:
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dot_vis = (i * 2) % 6 < 3
        if dot_vis:
            p.setPen(QPen(QColor(120, 120, 140, 150), 1.5))
            font = QFont("Arial", 10)
            p.setFont(font)
            p.drawText(int(SIZE * 0.62), int(SIZE * 0.16), "...")
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


# ═══════════════════════════════════════════════════════════════
#  绘制 primitives
# ═══════════════════════════════════════════════════════════════

def _draw_body(p: QPainter, w: int, cy: int) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(C_BODY))
    p.drawEllipse(QPoint(int(w * 0.5), int(cy + 10)),
                  int(w * 0.32), int(w * 0.28))
    p.setBrush(QBrush(C_EAR))
    le = QPainterPath()
    le.moveTo(w * 0.28, w * 0.32)
    le.lineTo(w * 0.38, w * 0.12)
    le.lineTo(w * 0.48, w * 0.30)
    p.drawPath(le)
    re = QPainterPath()
    re.moveTo(w * 0.52, w * 0.30)
    re.lineTo(w * 0.62, w * 0.12)
    re.lineTo(w * 0.72, w * 0.32)
    p.drawPath(re)


def _draw_face(p: QPainter, w: int, cy: int, blink: bool = True,
               smile: float = 0.3) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    # 脸盘
    p.setBrush(QBrush(C_FACE))
    p.drawEllipse(QPoint(int(w * 0.5), int(cy)),
                  int(w * 0.3), int(w * 0.26))
    # 眼睛
    if blink:
        _draw_eyes_open(p, w, cy)
    else:
        _draw_eyes_closed(p, w, cy)
    # 鼻子
    p.setBrush(QBrush(C_NOSE))
    p.drawEllipse(QPoint(int(w * 0.5), int(cy + 3)),
                  int(w * 0.025), int(SIZE * 0.02))
    # 嘴
    pen = QPen(C_MOUTH, 1.5)
    p.setPen(pen)
    mo = int(smile * 10)
    p.drawLine(int(w * 0.5), int(cy + 8),
               int(w * 0.44), int(cy + 15 - mo))
    p.drawLine(int(w * 0.5), int(cy + 8),
               int(w * 0.56), int(cy + 15 - mo))
    if smile > 0.3:
        p.drawLine(int(w * 0.44), int(cy + 15 - mo),
                   int(w * 0.56), int(cy + 15 - mo))


def _draw_eyes_open(p: QPainter, w: int, cy: int) -> None:
    eh = int(SIZE * 0.06)
    pw = int(w * 0.05)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(C_EYE))
    p.drawEllipse(QPoint(int(w * 0.38), int(cy - 6)), pw, eh)
    p.drawEllipse(QPoint(int(w * 0.62), int(cy - 6)), pw, eh)
    p.setBrush(QBrush(C_HIGHLIGHT))
    p.drawEllipse(QPoint(int(w * 0.40), int(cy - 9)),
                  int(w * 0.02), int(eh * 0.4))
    p.drawEllipse(QPoint(int(w * 0.64), int(cy - 9)),
                  int(w * 0.02), int(eh * 0.4))


def _draw_eyes_closed(p: QPainter, w: int, cy: int) -> None:
    p.setPen(QPen(C_EYE, 2))
    for ex in [w * 0.37, w * 0.63]:
        p.drawLine(int(ex - w * 0.04), int(cy - 6),
                   int(ex + w * 0.04), int(cy - 6))


def _draw_face_sleep(p: QPainter, w: int, cy: int) -> None:
    """睡觉时的完整脸部（闭眼 + 小嘴）。"""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(C_FACE))
    p.drawEllipse(QPoint(int(w * 0.5), int(cy)),
                  int(w * 0.3), int(w * 0.26))
    _draw_eyes_closed(p, w, cy)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(C_NOSE))
    p.drawEllipse(QPoint(int(w * 0.5), int(cy + 3)),
                  int(w * 0.025), int(SIZE * 0.02))
    pen = QPen(C_MOUTH, 1.5)
    p.setPen(pen)
    p.drawLine(int(w * 0.5), int(cy + 8),
               int(w * 0.48), int(cy + 13))
    p.drawLine(int(w * 0.5), int(cy + 8),
               int(w * 0.52), int(cy + 13))


# ═══════════════════════════════════════════════════════════════
#  New Base Layer — 特殊身体动作
# ═══════════════════════════════════════════════════════════════

def _gen_base_dance(fps: int = 10, frames: int = 10) -> AnimationClip:
    """跳舞：身体左右摇摆 + 弹跳。"""
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = i / max(1, frames - 1) * math.pi * 2
        sway = math.sin(t * 2) * 8  # 左右摇摆
        bounce = abs(math.sin(t)) * 8
        cy = int(SIZE * 0.52 + bounce)
        p.translate(int(sway), 0)
        _draw_body(p, SIZE, cy)
        _draw_face(p, SIZE, cy, blink=True, smile=0.5)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


def _gen_base_jump_rope(fps: int = 12, frames: int = 12) -> AnimationClip:
    """跳绳：高弹跳 + 手臂摆动。"""
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = i / max(1, frames - 1) * math.pi * 2
        jump = abs(math.sin(t * 1.5)) * 18  # 高弹跳
        cy = int(SIZE * 0.42 + jump)
        _draw_body(p, SIZE, cy)
        _draw_face(p, SIZE, cy, blink=True, smile=0.3)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


def _gen_base_spin(fps: int = 8, frames: int = 8) -> AnimationClip:
    """转圈圈：身体旋转。"""
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        angle = i / max(1, frames - 1) * 360
        cy = int(SIZE * 0.55)
        p.translate(SIZE // 2, SIZE // 2)
        p.rotate(angle)
        p.translate(-SIZE // 2, -SIZE // 2)
        _draw_body(p, SIZE, cy)
        _draw_face(p, SIZE, cy, blink=True, smile=0.3)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


# ═══════════════════════════════════════════════════════════════
#  New Overlay Layer — 新特效
# ═══════════════════════════════════════════════════════════════

def _gen_overlay_flower(fps: int = 10, frames: int = 10) -> AnimationClip:
    """撒花：彩色花瓣飘落 + 星星闪烁。"""
    pixmaps: list[QPixmap] = []
    colors = [
        QColor(255, 180, 200, 180), QColor(255, 220, 150, 180),
        QColor(200, 220, 255, 180), QColor(220, 255, 200, 180),
        QColor(255, 200, 220, 180),
    ]
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        t = i / max(1, frames - 1) * math.pi * 2
        for j in range(6):
            fx = int(SIZE * 0.15 + (i * 3 + j * 11) % 17 * SIZE * 0.04)
            fy = int(SIZE * 0.75 - (i + j * 5) % 14 * SIZE * 0.05)
            alpha = max(0, 200 - (i + j * 5) % 14 * 12)
            c = colors[j % len(colors)]
            c.setAlpha(alpha)
            p.setBrush(QBrush(c))
            p.drawEllipse(QPoint(fx, fy), 4, 3)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


def _gen_overlay_tear(fps: int = 8, frames: int = 8) -> AnimationClip:
    """大哭：蓝色泪滴下落。"""
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for j in range(3):
            tx = int(SIZE * 0.32 + j * SIZE * 0.14)
            ty = int(SIZE * 0.20 + ((i * 2 + j * 5) % 10) * SIZE * 0.04)
            alpha = max(0, 180 - (i + j * 3) % 10 * 16)
            p.setBrush(QBrush(QColor(100, 150, 255, alpha)))
            # 泪滴形状
            tear = QPainterPath()
            tear.moveTo(tx, ty - 4)
            tear.cubicTo(tx - 2, ty + 2, tx - 2, ty + 6, tx, ty + 6)
            tear.cubicTo(tx + 2, ty + 6, tx + 2, ty + 2, tx, ty - 4)
            p.drawPath(tear)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


def _gen_overlay_ball(fps: int = 8, frames: int = 8) -> AnimationClip:
    """顶足球：足球在头顶弹跳。"""
    pixmaps: list[QPixmap] = []
    for i in range(frames):
        pm = QPixmap(SIZE, SIZE)
        pm.fill(C_TRANSPARENT)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        t = i / max(1, frames - 1) * math.pi * 2
        ball_y = int(SIZE * 0.08 - abs(math.sin(t * 1.5)) * 15)
        ball_x = int(SIZE * 0.48 + math.sin(t) * 3)
        # 足球
        p.setBrush(QBrush(QColor(255, 255, 255, 200)))
        p.drawEllipse(QPoint(ball_x, ball_y), 10, 10)
        # 足球花纹
        p.setPen(QPen(QColor(40, 40, 40, 150), 1))
        p.drawLine(ball_x - 5, ball_y - 3, ball_x + 3, ball_y + 5)
        p.drawLine(ball_x + 5, ball_y - 3, ball_x - 3, ball_y + 5)
        p.drawEllipse(QPoint(ball_x, ball_y - 2), 2, 2)
        p.end()
        pixmaps.append(pm)
    return AnimationClip(pixmaps, fps)


# ═══════════════════════════════════════════════════════════════
#  Lazy factory: 按需生成，节省内存
# ═══════════════════════════════════════════════════════════════

_BUILTIN_FACTORIES: dict[str, callable] = {
    "base/idle":       lambda: _gen_base_idle(fps=15, frames=12),
    "base/wander":     lambda: _gen_base_idle(fps=15, frames=12),
    "base/sleep":      lambda: _gen_base_sleep(fps=10, frames=10),
    "base/dance":      lambda: _gen_base_dance(fps=12, frames=12),
    "base/jump_rope":  lambda: _gen_base_jump_rope(fps=15, frames=12),
    "base/spin":       lambda: _gen_base_spin(fps=10, frames=10),
    "expression/happy":   lambda: _gen_expr_happy(fps=15, frames=12),
    "expression/sad":     lambda: _gen_expr_sad(fps=10, frames=10),
    "expression/sleepy":  lambda: _gen_expr_sleepy(fps=10, frames=10),
    "overlay/heart":   lambda: _gen_overlay_heart(fps=12, frames=10),
    "overlay/zzz":     lambda: _gen_overlay_zzz(fps=10, frames=8),
    "overlay/dots":    lambda: _gen_overlay_dots(fps=8, frames=6),
    "overlay/flower":  lambda: _gen_overlay_flower(fps=12, frames=10),
    "overlay/tear":    lambda: _gen_overlay_tear(fps=10, frames=8),
    "overlay/ball":    lambda: _gen_overlay_ball(fps=10, frames=8),
}


def generate_builtin_clips() -> dict:
    """返回内置动画 lazy-factory 字典（不立即生成帧）。"""
    return dict(_BUILTIN_FACTORIES)
