"""音乐歌词环绕特效。

当检测到音乐软件正在播放时，将歌曲标题/歌词以 3D 圆环效果
环绕宠物旋转显示，每个字随机 RGB 颜色。
"""

import os
import re
import math
import random
import logging
import asyncio
import ctypes
from ctypes import wintypes
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRectF, QPropertyAnimation, QEasingCurve,
)
from PyQt6.QtGui import (
    QPainter, QPainterPath, QFont, QColor, QPen, QBrush,
)
from PyQt6.QtWidgets import QWidget

_log = logging.getLogger("music")

# ── 音乐软件关键词 ──
MUSIC_APPS = [
    "QQMusic", "QQ音乐", "Spotify", "网易云音乐", "netease",
    "Groove", "iTunes", "酷狗", "kugou", "foobar2000", "aimp",
    "QQMusic.exe", "cloudmusic", "YesPlayMusic", "Listen1",
    "lx-music", "musicfox", "Music", "音乐",
]

# ── 配置 ──
CHECK_INTERVAL_MS = 1500   # 检测间隔（歌词同步需要高频更新播放位置）
ROTATION_SPEED = -0.8       # 旋转速度（弧度/秒，负值=逆时针）
ORBIT_RADIUS = 110           # 环绕半径
FONT_SIZE_BASE = 18


class MusicVisualizer(QWidget):
    """透明覆盖层：3D 歌词环绕宠物旋转。"""

    def __init__(self, pet):
        super().__init__()
        self._pet = pet
        self._text = ""
        self._last_title = ""
        self._angle = 0.0
        self._smtc_position = 0.0
        self._glow_enabled = True
        self._colors: list[QColor] = []

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setFixedSize(300, 300)

        # 动画状态
        self._last_tick = 0
        self._animating = False

        # 检测计时器
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._check_music)
        self._check_timer.setInterval(CHECK_INTERVAL_MS)

        self.hide()

    def start(self):
        self._check_timer.start()
        _log.info("音乐可视化已启动")
        self._check_music()

    def set_glow_enabled(self, enabled: bool):
        self._glow_enabled = enabled  # 立即检测一次

    def stop(self):
        from tick_manager import TickManager
        TickManager.instance().unregister("music_viz")
        self._check_timer.stop()
        self.hide()
        _log.info("音乐可视化已停止")

    # ── 音乐检测 ──────────────────────────────────────────────

    def _check_music(self):
        """检测音乐 → 拿歌名 + 播放进度 → 查歌词。"""
        # 记录上次位置（在刷新前），用于检测真正的位置停滞
        prev_pos = self._smtc_position
        title = self._get_music_title()
        if not title:
            if self._animating:
                _log.info("音乐窗口已关闭")
                self._stop_animation()
            self._smtc_cache_time = 0.0
            self._smtc_cache_result = ""
            return

        # 检测位置停滞：超过 90s 没变化 → 音乐已停止
        if abs(self._smtc_position - prev_pos) < 0.1:
            self._stall_seconds = getattr(self, "_stall_seconds", 0.0) + CHECK_INTERVAL_MS / 1000
        else:
            self._stall_seconds = 0.0
        if self._stall_seconds > 90:
            _log.info("音乐位置长时间未变化，停止显示")
            self._stop_animation()
            return

        # 每轮都更新播放进度
        if title == self._last_title:
            tl = getattr(self, "_lyrics_timeline", None)
            if tl:
                pos = self._smtc_position
                idx = 0
                for i, (sec, _) in enumerate(tl):
                    if sec <= pos:
                        idx = i
                show = [t for _, t in tl[max(0, idx):idx + 1]]
                new_text = show[0] if show else ""
                _log.info(f"同步歌词 pos={pos:.1f}s idx={idx}/{len(tl)} → {new_text[:40]}")
                if new_text != self._text and new_text.strip():
                    self._text = new_text
                    self._generate_colors()
            return

        self._last_title = title
        clean = self._clean_title(title)
        _log.info(f"检测到歌曲: {clean!r}")

        # 尝试获取真实歌词
        lyrics = self._fetch_lyrics(clean)
        if lyrics:
            self._text = lyrics
            _log.info(f"获取到歌词 ({len(lyrics)}字)")
        else:
            # 获取失败 → 清除旧时间线 + 用歌名代替
            self._lyrics_timeline = []
            self._text = clean
            _log.info("未获取到歌词，显示歌名")

        self._generate_colors()
        self._start_animation()

    def _fetch_lyrics(self, title: str) -> str:
        """从网易云音乐 API 获取歌词（国内可访问）。"""
        parts = title.split(" - ", 1)
        song = parts[0].strip()
        artist = parts[1].strip() if len(parts) > 1 else ""

        cache_key = f"{song}|{artist}"
        if hasattr(self, "_lyrics_cache_key") and self._lyrics_cache_key == cache_key:
            return getattr(self, "_lyrics_cache_result", "")

        try:
            import requests

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://music.163.com/",
            }

            # 1) 搜索歌曲 ID
            resp = requests.post(
                "https://music.163.com/api/search/get",
                data={"s": f"{song} {artist}", "type": 1, "limit": 3},
                headers=headers, timeout=5,
            )
            songs = resp.json().get("result", {}).get("songs", [])
            if not songs:
                self._lyrics_cache_key = cache_key
                self._lyrics_cache_result = ""
                return ""

            sid = songs[0]["id"]

            # 2) 获取歌词
            resp2 = requests.get(
                f"https://music.163.com/api/song/lyric?id={sid}&lv=1",
                headers=headers, timeout=5,
            )
            lrc = resp2.json().get("lrc", {}).get("lyric", "")
            if not lrc:
                self._lyrics_cache_key = cache_key
                self._lyrics_cache_result = ""
                return ""

            # 3) 解析时间标签，存储 (seconds, text) 列表
            parsed = re.findall(r"\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)", lrc)
            if parsed:
                timeline = []
                for m, s, ms, text in parsed:
                    sec = int(m) * 60 + int(s) + int(ms) / (10 ** len(ms))
                    text = text.strip()
                    if text and not any(text.startswith(w) for w in
                            ("作词", "作曲", "编曲", "制作人", "混音", "录音", "和声", "吉他", "钢琴", "键盘", "贝斯", "鼓", "弦乐", "监制", "OP", "SP")):
                        timeline.append((sec, text))
                self._lyrics_timeline = sorted(timeline, key=lambda x: x[0])
                # 初始显示第一行
                result = self._lyrics_timeline[0][1] if self._lyrics_timeline else ""
            else:
                # 没有时间标签 → 普通歌词
                cleaned = re.sub(r"\[\d{2}:\d{2}\.\d{2,3}\]", "", lrc)
                lines = [l.strip() for l in cleaned.split("\n") if l.strip()
                         and not any(l.strip().startswith(w) for w in
                            ("作词", "作曲", "编曲", "制作人", "混音", "录音", "和声", "吉他", "钢琴", "键盘", "贝斯", "鼓", "弦乐", "监制", "OP", "SP"))]
                self._lyrics_timeline = []
                self._lyrics_lines = lines
                self._lyrics_page = 0
                result = lines[0] if lines else ""
            self._lyrics_cache_key = cache_key
            self._lyrics_cache_result = result
            return result if result else ""
        except Exception as e:
            _log.debug(f"歌词查询失败: {e}")
            return ""

    def _get_music_title(self) -> str:
        """获取当前播放歌曲：优先 SMTC API，其次窗口标题。"""
        # 1) Windows SystemMediaTransportControls（实时歌名）
        song = self._get_smtc_song()
        if song:
            return song

        # 2) EnumWindows 扫描窗口标题
        titles: list[str] = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL,
            wintypes.HWND, wintypes.LPARAM)

        def _enum_callback(hwnd, _lparam):
            buf = (ctypes.c_wchar * 512)()
            length = ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
            if length > 0:
                t = buf[:length]
                low = t.lower()
                if not any(x in low for x in (
                    "gdi+", "msctf", "default ime", "olemainthread",
                    "dde", "ime", "task host",
                )):
                    titles.append(t)
            return True

        try:
            ctypes.windll.user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)
        except Exception:
            return ""

        matches: list[str] = []
        for title in titles:
            for keyword in MUSIC_APPS:
                if keyword.lower() in title.lower():
                    matches.append(title)
                    break

        if not matches:
            return ""

        for t in sorted(matches, key=len, reverse=True):
            if " - " in t and len(t) > 10:
                return t

        pure_names = {"网易云音乐", "qq音乐", "qqmusic", "spotify",
                       "netease", "cloudmusic", "酷狗音乐", "kugou"}
        for t in sorted(matches, key=len, reverse=True):
            if t.strip().lower() not in pure_names and len(t) > 2:
                return t

        return matches[0]

    def _get_smtc_song(self) -> str:
        """通过 WinRT 获取当前播放歌曲 + 播放进度。"""
        now = __import__("time").time()
        if hasattr(self, "_smtc_cache_time") and now - self._smtc_cache_time < 0.5:
            return getattr(self, "_smtc_cache_result", "")

        try:
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager,
            )

            async def _get():
                mgr = await GlobalSystemMediaTransportControlsSessionManager.request_async()
                s = mgr.get_current_session()
                if not s:
                    return "", 0.0, False
                info = await s.try_get_media_properties_async()
                timeline = s.get_timeline_properties()
                pos = timeline.position.total_seconds() if timeline and timeline.position else 0.0
                # 检查播放状态（Playing=4, Paused=5, Stopped=6）
                pb = s.get_playback_info()
                playing = (pb.playback_status.value if pb and pb.playback_status else 4) == 4
                if info and info.title:
                    artist = info.artist or ""
                    title = f"{info.title} - {artist}" if artist else info.title
                    return title, pos, playing
                return "", 0.0, False

            result, position, playing = asyncio.run(_get())
        except ImportError:
            result, position, playing = "", 0.0, False
        except Exception:
            result, position, playing = "", 0.0, False

        self._smtc_cache_time = now
        self._smtc_cache_result = result

        # ── 自计时（SMTC 不给位置时使用）──
        if result and not hasattr(self, "_song_title"):
            self._song_title = ""
            self._song_start_time = now
            self._pause_accum = 0.0
            self._pause_start = 0.0

        # 切歌 → 重置
        if result and result != self._song_title:
            self._song_title = result
            self._song_start_time = now
            self._pause_accum = 0.0
            self._pause_start = 0.0

        if position <= 0 and result:
            if playing:
                if self._pause_start > 0:
                    self._pause_accum += now - self._pause_start
                    self._pause_start = 0.0
                position = now - self._song_start_time - self._pause_accum
            else:
                if self._pause_start == 0.0:
                    self._pause_start = now
                position = self._smtc_position  # 冻结
        elif position > 0:
            # 检测 seek：SMTC 位置和自计时预测相差 > 3s 则判定为拖拽进度条
            if hasattr(self, "_song_start_time"):
                expected = now - self._song_start_time - self._pause_accum
                if abs(position - expected) > 3.0:
                    _log.info(f"检测到进度跳转: {expected:.1f}s → {position:.1f}s")
                    self._pause_accum = 0.0
                    self._pause_start = 0.0
            self._song_start_time = now - position

        self._smtc_position = max(0.0, position)
        if result:
            _log.info(f"SMTC: {result[:20]!r}  pos={position:.1f}s  " +
                      ("[PLAY]" if playing else "[PAUSE]"))
        return result

    def _clean_title(self, raw: str) -> str:
        """提取干净的歌名（去掉软件名后缀）。"""
        # 网易云: "歌曲名 - 歌手 - 网易云音乐" 或 "网易云音乐"
        # QQ音乐: "歌曲名 - QQ音乐" 或 "QQ音乐"
        # Spotify: "歌曲名 - Spotify" 或 "Spotify Premium"
        suffixes = [
            " - QQ音乐", " - QQMusic", " - Spotify", " - 网易云音乐",
            " - Netease", " - Groove Music", " - foobar2000",
            "  QQ音乐", "  Spotify", "  网易云音乐",
            "网易云音乐", "QQ音乐", "Spotify",
        ]
        for s in suffixes:
            if raw.endswith(s):
                raw = raw[:-len(s)].strip(" -")
        # 过滤掉纯粹的软件名
        raw = raw.strip()[:40]
        if raw.lower() in {"netease", "cloudmusic", "spotify", "qqmusic",
                            "网易云音乐", "qq音乐"}:
            return "♪ 音乐播放中 ♪"
        if not raw:
            return "♪ ♪ ♪"
        return raw

    # ── 动画 ──────────────────────────────────────────────────

    def _start_animation(self):
        from tick_manager import TickManager
        TickManager.instance().register("music_viz", self._tick, 33)
        self._animating = True
        self._position_overlay()
        self.show()
        self.raise_()
        _log.info(f"检测到音乐: {self._text}")

    def _stop_animation(self):
        from tick_manager import TickManager
        TickManager.instance().unregister("music_viz")
        self._animating = False
        self.hide()

    def _tick(self):
        import time
        now = time.perf_counter_ns() / 1e9
        dt = now - self._last_tick if self._last_tick else 0.033
        self._last_tick = now
        self._angle += ROTATION_SPEED * dt

        # 降低 raise_() 频率：500ms 一次即可
        if not hasattr(self, "_last_raise") or now - self._last_raise > 0.5:
            self._last_raise = now
            self.raise_()  # 保持在宠物上层

        # 无 LRC 时间轴 → 每 5 秒翻一行
        if not getattr(self, "_lyrics_timeline", None) and hasattr(self, "_lyrics_lines") and self._lyrics_lines:
            page = int(now / 5) % len(self._lyrics_lines)
            if page != getattr(self, "_lyrics_page", 0):
                self._lyrics_page = page
                self._text = self._lyrics_lines[page]
                self._generate_colors()

        self._position_overlay()
        self.update()

    def _position_overlay(self):
        """窗口居中覆盖在宠物上方。"""
        pet_geo = self._pet.frameGeometry()
        cx = pet_geo.center().x() - self.width() // 2
        cy = pet_geo.center().y() - self.height() // 2
        self.move(cx, cy)

    def _generate_colors(self):
        """为每个字符生成随机亮色。"""
        self._colors = []
        for _ in self._text:
            r = random.randint(80, 255)
            g = random.randint(80, 255)
            b = random.randint(80, 255)
            # 确保整体偏亮
            if r + g + b < 350:
                r = min(255, r + 80)
                g = min(255, g + 80)
                b = min(255, b + 80)
            self._colors.append(QColor(r, g, b, 220))

    # ── 绘制 ──────────────────────────────────────────────────

    def paintEvent(self, event):
        if not self._text:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        # 音乐光环：三圈渐变波纹，随旋转呼吸变色
        if self._glow_enabled:
            for ring in range(3):
                r = w // 2 - 6 - ring * 10
                phase = self._angle * (0.7 + ring * 0.3)
                glow = QColor(
                    abs(int(140 + 60 * math.sin(phase))),
                    abs(int(170 + 40 * math.sin(phase + 1.2))),
                    abs(int(210 + 45 * math.sin(phase + 2.5))),
                    100 - ring * 25,
                )
                p.setPen(QPen(glow, 2.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        text = self._text
        n = len(text)

        # 根据字符数调整弧线跨度，字少拉大间距
        arc_span = min(280, n * 26)
        start_deg = 270 - arc_span / 2
        offset = math.degrees(self._angle) % 360
        arc_radius = ORBIT_RADIUS * 0.85

        for i, ch in enumerate(text):
            progress = i / max(1, n - 1) if n > 1 else 0.5
            deg = start_deg + progress * arc_span + offset
            angle = math.radians(deg)

            x = cx + arc_radius * math.cos(angle)
            y = cy - arc_radius * 0.35 * math.sin(angle)

            # 中间亮大，两侧暗小
            dist = abs(progress - 0.5)
            alpha = int(250 - dist * 200)
            size = int(FONT_SIZE_BASE * (1.0 - dist * 0.6))

            if self._colors:
                color = QColor(self._colors[i % len(self._colors)])
            else:
                color = QColor(200, 200, 200)
            color.setAlpha(max(20, alpha))

            font = QFont("Microsoft YaHei", size)
            font.setBold(dist < 0.1)
            p.setFont(font)
            p.setPen(QPen(color))
            # 更宽的绘制区域
            p.drawText(QRectF(x - 22, y - 14, 44, 28),
                       Qt.AlignmentFlag.AlignCenter, ch)

        p.end()
