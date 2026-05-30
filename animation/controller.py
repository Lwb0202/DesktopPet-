"""AnimationController — 分层动画控制器 + 帧合成器。

管理 Base / Expression / Overlay 三层，每 tick 更新所有 layer
并通过 QPainter 合成最终帧。
"""

from __future__ import annotations
import os
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QPainter, QColor, QBrush
from .clip import AnimationClip
from .layer import AnimationLayer
from .builtin import generate_builtin_clips


# 默认帧率
DEFAULT_FPS = 12


class AnimationController:
    """分层动画控制器。

    Layers:
        base        — 身体动作（idle / wander / sleep）
        expression  — 表情叠加（happy / sad / sleepy）
        overlays    — 特效叠加（heart / zzz / dots）

    用法::

        ctrl = AnimationController(pet_dir)
        ctrl.set_base("idle")
        ctrl.set_expression("happy")
        ctrl.set_overlay("heart", True)

        # 每帧 (~16ms) 调用:
        ctrl.update(16)
        pixmap = ctrl.composite()
    """

    __slots__ = ("_size", "_clips", "_clip_factories", "base", "expression",
                 "overlays", "_frame_cache", "_dirty")

    def __init__(self, pet_path: str | None = None):
        """
        Args:
            pet_path: 宠物资源目录路径。
                      None → 使用内置程序化动画。
                      目录 → 按 assets/ 子目录加载 PNG 序列。
        """
        self._size = QSize(128, 128)
        self._clips: dict[str, AnimationClip] = {}

        # 三层结构
        self.base = AnimationLayer()
        self.expression = AnimationLayer()
        self.overlays: dict[str, AnimationLayer] = {
            "heart":  AnimationLayer(visible=False),
            "zzz":    AnimationLayer(visible=False),
            "dots":   AnimationLayer(visible=False),
            "flower": AnimationLayer(visible=False),
            "tear":   AnimationLayer(visible=False),
            "ball":   AnimationLayer(visible=False),
        }

        self._frame_cache: QPixmap | None = None
        self._dirty = True
        self._clip_factories: dict[str, callable] = {}

        # 加载资源（内置 clip 用 lazy factory，不立即生成帧）
        if pet_path and os.path.isdir(pet_path):
            self._load_from_directory(pet_path)
        else:
            self._clip_factories = generate_builtin_clips()

        # 初始状态
        self.set_base("idle")

    # ── lazy-load ──────────────────────────────────────────────

    def _get_clip(self, key: str) -> AnimationClip | None:
        """获取 clip：优先缓存，否则从 factory 生成。"""
        clip = self._clips.get(key)
        if clip is not None:
            return clip
        factory = self._clip_factories.get(key)
        if factory:
            clip = factory()
            self._clips[key] = clip
            return clip
        return None

    # ── 资源加载 ──────────────────────────────────────────────

    def _load_from_directory(self, pet_path: str) -> None:
        """从宠物目录加载分层 PNG 序列。

        期望结构::

            pet_path/
                assets/base/idle/*.png
                assets/base/sleep/*.png
                assets/expression/happy/*.png
                assets/overlay/heart/*.png
                ...

        若 PNG 序列不存在，回退到旧 GIF 格式。
        """
        clip_dirs = [
            # (key, relative_dir, fps)
            ("base/idle",      "assets/base/idle",      12),
            ("base/wander",    "assets/base/idle",      12),
            ("base/sleep",     "assets/base/sleep",      8),
            ("base/dance",     "assets/base/dance",     10),
            ("base/jump_rope", "assets/base/jump_rope", 12),
            ("base/spin",      "assets/base/spin",       8),
            ("expression/happy",  "assets/expression/happy",  12),
            ("expression/sad",    "assets/expression/sad",     8),
            ("expression/sleepy", "assets/expression/sleepy",  8),
            ("overlay/heart",  "assets/overlay/heart",  10),
            ("overlay/zzz",    "assets/overlay/zzz",     8),
            ("overlay/dots",   "assets/overlay/dots",    6),
            ("overlay/flower", "assets/overlay/flower", 10),
            ("overlay/tear",   "assets/overlay/tear",    8),
            ("overlay/ball",   "assets/overlay/ball",    8),
        ]
        for key, rel_dir, fps in clip_dirs:
            clip = AnimationClip.from_directory(
                os.path.join(pet_path, rel_dir), fps=fps
            )
            if clip is None:
                # 回退到旧 GIF
                gif_name = key.split("/")[-1] + ".gif"
                gif_path = os.path.join(pet_path, gif_name)
                if os.path.isfile(gif_path):
                    clip = AnimationClip.from_gif(gif_path, fps=fps)
            if clip is not None:
                self._clips[key] = clip

        # 从首帧确定尺寸
        for clip in self._clips.values():
            s = clip.size
            if s.width() > 0 and s.height() > 0:
                self._size = s
                break

    # ── 每帧更新 ──────────────────────────────────────────────

    def update(self, dt_ms: float) -> None:
        """推进所有图层的动画时间。"""
        self.base.update(dt_ms)
        self.expression.update(dt_ms)
        for ov in self.overlays.values():
            ov.update(dt_ms)
        self._dirty = True

    # ── 帧合成 ────────────────────────────────────────────────

    def composite(self) -> QPixmap:
        """合成当前帧：base → expression → overlay[heart] → overlay[zzz] → overlay[dots]。"""
        if not self._dirty and self._frame_cache is not None:
            return self._frame_cache

        result = QPixmap(self._size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 0. 地面阴影（最先绘制，位于底层）
        w, h = self._size.width(), self._size.height()
        shadow_w, shadow_h = int(w * 0.50), int(h * 0.08)
        sx = int(w * 0.5) - shadow_w // 2
        sy = int(h * 0.90) - shadow_h // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 50)))
        painter.drawEllipse(sx, sy, shadow_w, shadow_h)

        # 1. Base
        self._paint_layer(painter, self.base)

        # 2. Expression
        self._paint_layer(painter, self.expression)

        # 3. Overlays (按固定顺序：粒子/文字在上层)
        for name in ("ball", "heart", "flower", "tear", "zzz", "dots"):
            self._paint_layer(painter, self.overlays[name])

        painter.end()
        self._frame_cache = result
        self._dirty = False
        return result

    @staticmethod
    def _paint_layer(painter: QPainter, layer: AnimationLayer) -> None:
        frame = layer.frame
        if frame is not None and not frame.isNull():
            if layer.opacity < 1.0:
                painter.setOpacity(layer.opacity)
            painter.drawPixmap(0, 0, frame)
            if layer.opacity < 1.0:
                painter.setOpacity(1.0)

    # ── 动画控制 API ──────────────────────────────────────────

    def set_base(self, name: str) -> None:
        """切换身体动画。

        Args:
            name: "idle" | "wander" | "sleep"
        """
        key = f"base/{name}"
        clip = self._get_clip(key)
        if clip:
            self.base.play(clip)
            self._update_size(clip)

    def set_expression(self, name: str | None) -> None:
        """切换表情层。

        Args:
            name: "happy" | "sad" | "sleepy" | None（隐藏表情层）
        """
        if name is None:
            self.expression.stop()
            self.expression.visible = False
            return
        key = f"expression/{name}"
        clip = self._get_clip(key)
        if clip:
            self.expression.visible = True
            self.expression.play(clip)

    def set_overlay(self, name: str, enabled: bool) -> None:
        """开关特效层。

        Args:
            name: "heart" | "zzz" | "dots"
            enabled: True=显示, False=隐藏
        """
        layer = self.overlays.get(name)
        if layer is None:
            return
        if enabled:
            clip = self._get_clip(f"overlay/{name}")
            if clip:
                layer.visible = True
                layer.play(clip)
        else:
            layer.visible = False
            layer.stop()

    # ── 尺寸 ──────────────────────────────────────────────────

    def _update_size(self, clip: AnimationClip) -> None:
        s = clip.size
        if s.width() > 0 and s.height() > 0:
            self._size = s

    @property
    def size(self) -> QSize:
        return self._size
