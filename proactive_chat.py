"""宠物主动说话。

定时根据时间、天气、用户行为、今日热点等上下文，通过 AI 生成一句
自然的话，以气泡形式展示。不打开对话框，纯被动推送。
"""

import random
import time
import logging
import datetime
from PyQt6.QtCore import QTimer, QObject, pyqtSignal

_log = logging.getLogger("proactive")

# 知乎热榜 API（免费，无需 Key）
ZHIHU_HOT_URL = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=6"


class ProactiveChat(QObject):
    """间隔一定时间，主动发起一句 AI 对话并以气泡展示。"""

    _speak_ready = pyqtSignal(str)  # 跨线程：后台线程 → 主线程

    def __init__(self, pet, memory_manager=None, emotion_manager=None,
                 companion=None, interval_minutes: int = 20,
                 companion_days: int = 0):
        super().__init__()
        self._pet = pet
        self._memory = memory_manager
        self._emotion = emotion_manager
        self._companion = companion
        self._companion_days = companion_days
        self._interval_ms = interval_minutes * 60_000
        self._enabled = True

        self._timer = QTimer()
        self._timer.timeout.connect(self._maybe_speak)
        self._timer.setSingleShot(True)

        self._speak_ready.connect(self._show_bubble)

        # 热点缓存
        self._topics_cache: list[str] = []
        self._topics_cache_time = 0.0

    def start(self):
        self._schedule_next()

    def stop(self):
        self._timer.stop()

    def set_interval(self, minutes: int):
        """运行时修改间隔（下次触发生效）。"""
        self._interval_ms = minutes * 60_000
        _log.info(f"主动说话间隔改为 {minutes} 分钟")

    # ── 调度 ──────────────────────────────────────────────────

    def _schedule_next(self):
        if not self._enabled:
            return
        jitter = random.randint(-120_000, 120_000)
        delay = max(60_000, self._interval_ms + jitter)
        self._timer.start(delay)

    # ── 热点获取 ──────────────────────────────────────────────

    def _get_hot_topics(self) -> list[str]:
        """获取今日热点标题（知乎热榜，缓存 30 分钟）。"""
        now = time.time()
        if self._topics_cache and (now - self._topics_cache_time) < 1800:
            return self._topics_cache

        try:
            import requests
            resp = requests.get(
                ZHIHU_HOT_URL,
                headers={"User-Agent": "DesktopPet/1.0"},
                timeout=5,
            )
            data = resp.json().get("data", [])
            titles = []
            for item in data[:5]:
                t = item.get("target", {}).get("title", "")
                if t:
                    titles.append(t)
            if titles:
                self._topics_cache = titles
                self._topics_cache_time = now
                _log.info(f"获取到 {len(titles)} 条热点: {titles[0][:30]}...")
            return titles
        except Exception:
            _log.debug("热点获取失败，使用缓存")
            return self._topics_cache

    # ── 说话逻辑 ──────────────────────────────────────────────

    def _maybe_speak(self):
        try:
            self._do_speak()
        except Exception:
            _log.exception("主动说话失败")
        finally:
            self._schedule_next()

    def _do_speak(self):
        ctx_parts = ["你是一只可爱的桌面宠物猫咪，正在主动对主人说一句话。"]

        if self._companion_days > 0:
            ctx_parts.append(f"你陪伴主人已经 {self._companion_days} 天了。")

        now = datetime.datetime.now()
        hour = now.hour
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        ctx_parts.append(f"今天是{weekday}。")

        if 6 <= hour < 9:
            ctx_parts.append("现在是早晨。")
        elif 9 <= hour < 12:
            ctx_parts.append("现在是上午。")
        elif 12 <= hour < 14:
            ctx_parts.append("现在是中午。")
        elif 14 <= hour < 18:
            ctx_parts.append("现在是下午。")
        elif 18 <= hour < 22:
            ctx_parts.append("现在是晚上。")
        else:
            ctx_parts.append("现在是深夜。")

        # 今日热点
        topics = self._get_hot_topics()
        if topics:
            topic_lines = "\n".join(f"  - {t}" for t in topics[:3])
            ctx_parts.append(f"今天的热搜/热点话题：\n{topic_lines}")

        # 情绪
        if self._emotion:
            mood = self._emotion.ai_context()
            if mood:
                ctx_parts.append(mood)

        # 项目
        if self._companion:
            prj_ctx = self._companion.get_context_for_ai()
            if prj_ctx:
                ctx_parts.append(prj_ctx)

        # 记忆
        if self._memory:
            mem_ctx = self._memory.get_context_for_ai()
            if mem_ctx:
                ctx_parts.append(mem_ctx)

        ctx_parts.append(
            "要求：用中文回复，说1-2句话（25字以内），语气可爱自然。"
            "你可以聊聊今天的热点话题、关心主人的工作状态、或者单纯撒娇。"
            "如果提到了热点，要自然地带出来，不要像播报新闻。"
            "不要加前缀和引号。"
        )

        prompt = "\n".join(ctx_parts)
        _log.info(f"主动说话 prompt 长度: {len(prompt)} 字")

        # 后台线程调用 AI，避免阻塞动画
        import threading
        threading.Thread(target=self._speak_thread, args=(prompt,), daemon=True).start()

    def _speak_thread(self, prompt):
        """后台线程：调用 AI，主线程展示结果。"""
        from ai.doubao_api import DoubaoChat
        try:
            bot = DoubaoChat()
            reply = bot.chat(prompt)
            bot.clear_context()
        except Exception:
            _log.exception("主动说话 API 失败")
            return

        if reply:
            reply = reply.strip().strip('"''「」')
            if len(reply) > 40:
                reply = reply[:40]
            _log.info(f"宠物主动说: {reply!r}")
            self._speak_ready.emit(reply)  # 跨线程信号 → 主线程 slot

    def _show_bubble(self, reply: str):
        """主线程：显示气泡。"""
        self._pet.show_bubble(reply)
