"""AnimationClip — PNG 序列帧动画片段。

支持从目录加载 PNG 序列、从 GIF 提取帧、或直接传入 QPixmap 列表。
独立 FPS 控制，循环/单次播放。
"""

from __future__ import annotations
import os
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QMovie


class AnimationClip:
    """单个动画片段：一组帧 + FPS + 循环控制。"""

    __slots__ = ("_frames", "_fps", "_loop", "_index", "_elapsed", "_finished")

    def __init__(self, frames: list[QPixmap], fps: int = 12, loop: bool = True):
        self._frames = frames
        self._fps = max(1, fps)
        self._loop = loop
        self._index = 0
        self._elapsed = 0.0
        self._finished = False

    # ── 属性 ──────────────────────────────────────────────────

    @property
    def frame(self) -> QPixmap | None:
        """当前帧。无帧时返回 None。"""
        if not self._frames:
            return None
        return self._frames[self._index]

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def fps(self) -> int:
        return self._fps

    @property
    def finished(self) -> bool:
        """单次播放是否已结束（循环模式永远 False）。"""
        return self._finished

    @property
    def size(self):
        """首帧尺寸，用于布局计算。"""
        if self._frames and not self._frames[0].isNull():
            return self._frames[0].size()
        from PyQt6.QtCore import QSize
        return QSize(128, 128)

    # ── 播放控制 ──────────────────────────────────────────────

    def update(self, dt_ms: float) -> None:
        """推进动画时间。dt_ms 为距上次调用的毫秒数。"""
        if self._finished or not self._frames or len(self._frames) <= 1:
            return
        self._elapsed += dt_ms
        frame_ms = 1000.0 / self._fps
        while self._elapsed >= frame_ms:
            self._elapsed -= frame_ms
            self._index += 1
            if self._index >= len(self._frames):
                if self._loop:
                    self._index = 0
                else:
                    self._index = len(self._frames) - 1
                    self._finished = True
                    break

    def reset(self) -> None:
        """重置到第一帧。"""
        self._index = 0
        self._elapsed = 0.0
        self._finished = False

    def seek(self, index: int) -> None:
        """跳转到指定帧（自动钳制）。"""
        self._index = max(0, min(index, len(self._frames) - 1)) if self._frames else 0
        self._elapsed = 0.0
        self._finished = False

    # ── 工厂方法 ──────────────────────────────────────────────

    @staticmethod
    def from_directory(path: str, fps: int = 12, loop: bool = True
                       ) -> AnimationClip | None:
        """从目录加载 PNG 序列（000.png, 001.png, ...）。

        返回 None 表示目录不存在或无有效 PNG。
        """
        if not path or not os.path.isdir(path):
            return None
        frames: list[QPixmap] = []
        for name in sorted(os.listdir(path)):
            if name.lower().endswith(".png"):
                pm = QPixmap(os.path.join(path, name))
                if not pm.isNull():
                    frames.append(pm)
        return AnimationClip(frames, fps, loop) if frames else None

    @staticmethod
    def from_gif(path: str, fps: int = 12, loop: bool = True
                 ) -> AnimationClip | None:
        """从 GIF 文件提取帧序列。兼容旧资源格式。"""
        if not path or not os.path.isfile(path):
            return None
        movie = QMovie(path)
        frames: list[QPixmap] = []
        movie.jumpToFrame(0)
        while True:
            pm = movie.currentPixmap()
            if pm.isNull():
                break
            frames.append(QPixmap(pm))  # 深拷贝
            if not movie.jumpToNextFrame():
                break
        movie.stop()
        return AnimationClip(frames, fps, loop) if frames else None

    @staticmethod
    def from_pixmaps(pixmaps: list[QPixmap], fps: int = 12, loop: bool = True
                     ) -> AnimationClip:
        """直接从 QPixmap 列表创建（程序化生成帧时使用）。"""
        return AnimationClip(list(pixmaps), fps, loop)
