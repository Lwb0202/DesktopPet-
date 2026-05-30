"""AnimationLayer — 单个动画图层。

持有当前 AnimationClip，支持运行时切换、淡入淡出（预留）、独立可见性。
"""

from __future__ import annotations
from PyQt6.QtGui import QPixmap


class AnimationLayer:
    """一个动画图层：绑定 clip + 可见性 + 透明度。

    组合关系：AnimationController 持有多个 AnimationLayer。
    """

    __slots__ = ("_clip", "_visible", "_opacity")

    def __init__(self, visible: bool = True):
        self._clip: "AnimationClip | None" = None  # noqa: F821
        self._visible = visible
        self._opacity = 1.0

    # ── 属性 ──────────────────────────────────────────────────

    @property
    def frame(self) -> QPixmap | None:
        """当前可见帧。隐藏或无 clip 时返回 None。"""
        if not self._visible or self._clip is None:
            return None
        fm = self._clip.frame
        if fm is None or fm.isNull():
            return None
        return fm

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, v: bool) -> None:
        self._visible = v

    @property
    def opacity(self) -> float:
        return self._opacity

    @opacity.setter
    def opacity(self, v: float) -> None:
        self._opacity = max(0.0, min(1.0, v))

    @property
    def clip(self):
        return self._clip

    @property
    def playing(self) -> bool:
        return self._clip is not None

    # ── 播放控制 ──────────────────────────────────────────────

    def play(self, clip) -> None:
        """切换到新 clip 并从头播放。传入 None 等同于 stop()。"""
        if clip is None:
            self.stop()
            return
        if self._clip is not clip:
            self._clip = clip
            clip.reset()

    def stop(self) -> None:
        """停止播放（保留可见性设置）。"""
        self._clip = None

    def update(self, dt_ms: float) -> None:
        """推进当前 clip 的时间。"""
        if self._clip:
            self._clip.update(dt_ms)
