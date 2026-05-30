"""情绪状态管理 —— 30 分钟持续情绪，影响气泡/动画/AI 对话。

不重构现有 AI 系统，仅作为附加层注入情绪上下文。
"""

import time
import random
import logging
from enum import Enum

_log = logging.getLogger("emotion")


# ═══════════════════════════════════════════════════════════════
#  情绪枚举
# ═══════════════════════════════════════════════════════════════

class Emotion(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"


# ═══════════════════════════════════════════════════════════════
#  负面关键词（简单中文匹配，不引入 NLP 依赖）
# ═══════════════════════════════════════════════════════════════

NEGATIVE_KEYWORDS = [
    "烦", "累", "难过", "不开心", "生气", "讨厌", "无聊",
    "困", "郁闷", "烦躁", "焦虑", "崩溃", "失败", "难受",
    "压力", "好烦", "好累", "好难", "不想", "哭了", "绝望",
    "emo", "好气", "烦死了", "累死了", "不行了", "没意思",
    "想哭", "心累", "无语", "麻了", "栓Q",
]

POSITIVE_KEYWORDS = [
    "开心", "高兴", "哈哈", "好耶", "nice", "太棒了",
    "厉害", "不错", "快乐", "嘻嘻", "嘿嘿", "谢谢",
    "喜欢", "爱", "好棒", "牛", "绝了", "舒服",
]


# ═══════════════════════════════════════════════════════════════
#  按情绪分组的对话气泡
# ═══════════════════════════════════════════════════════════════

NEUTRAL_BUBBLES = [
    "你好呀~", "今天天气不错呢", "有点困...", "陪我玩嘛！",
    "不要点我 >_<", "喵~", "好无聊呀", "肚子饿了...",
    "加油！", "^^", "......", "哼！",
    "摸摸头~", "诶？", "嘻嘻", "我在思考喵生...",
    "别戳了！", "来玩嘛~",
]

HAPPY_BUBBLES = [
    "嘿嘿，好开心~", "今天真棒！", "啦啦啦~", "♪ 心情好 ~",
    "来玩来玩！", "嘻嘻嘻", "你真好！", "开心到飞起！",
    "今天运气不错呢~", "耶！", "我好喜欢你呀~",
    "喵呜~ 好幸福", "蹦蹦跳跳！", "✧ 闪闪发光 ✧",
]

SAD_BUBBLES = [
    "嗯...", "有点累", "不太想动", "好吧",
    "......", "喵...", "让我静静", "不想说话",
    "随便你", "哦", "算了", "还行吧",
    "我没事", "你忙你的", "...嗯", "",
]

# ── AI 情绪上下文 ──

EMOTION_AI_CONTEXT = {
    Emotion.NEUTRAL: "",
    Emotion.HAPPY: "宠物现在心情很好，活泼开朗。",
    Emotion.SAD: "宠物现在情绪有些低落，话比较少，不太想动。",
}


# ═══════════════════════════════════════════════════════════════
#  状态权重修正（乘到 HAPPY/WANDER/SLEEP/STARE 权重上）
# ═══════════════════════════════════════════════════════════════

EMOTION_WEIGHT_MODIFIERS = {
    Emotion.NEUTRAL: {"HAPPY": 1.0, "WANDER": 1.0, "SLEEP": 1.0, "STARE": 1.0},
    Emotion.HAPPY:  {"HAPPY": 2.5, "WANDER": 1.5, "SLEEP": 0.3, "STARE": 0.2},
    Emotion.SAD:    {"HAPPY": 0.1, "WANDER": 0.3, "SLEEP": 2.0, "STARE": 2.5},
}


# ═══════════════════════════════════════════════════════════════
#  EmotionManager
# ═══════════════════════════════════════════════════════════════

class EmotionManager:
    """30 分钟持续情绪，支持外部事件驱动转换。

    Usage::

        em = EmotionManager()
        em.on_click()            # 记录点击
        em.on_chat(user_msg)     # 分析聊天情绪
        bubble = em.pick_bubble()# 获取当前情绪的气泡
        ctx = em.ai_context()    # 获取 AI 注入上下文
        modifier = em.weight_modifier()  # 获取动画权重修正
    """

    DURATION_SEC = 30 * 60       # 情绪持续时间
    CLICK_THRESHOLD = 5          # 10 秒内点击次数 → HAPPY
    CLICK_WINDOW_SEC = 10

    def __init__(self):
        self._emotion = Emotion.NEUTRAL
        self._set_at = time.time()
        self._clicks: list[float] = []  # 点击时间戳

    # ── 属性 ──────────────────────────────────────────────────

    @property
    def current(self) -> Emotion:
        """当前情绪（过期自动降回 NEUTRAL）。"""
        if (self._emotion != Emotion.NEUTRAL
                and time.time() - self._set_at > self.DURATION_SEC):
            self._emotion = Emotion.NEUTRAL
            self._set_at = time.time()
        return self._emotion

    @property
    def seconds_remaining(self) -> float:
        """距离情绪过期还有多少秒。"""
        elapsed = time.time() - self._set_at
        return max(0, self.DURATION_SEC - elapsed)

    # ── 事件输入 ──────────────────────────────────────────────

    def on_click(self) -> None:
        """记录一次点击。频繁点击可提升为 HAPPY。"""
        now = time.time()
        self._clicks.append(now)
        # 只保留窗口内的点击
        cutoff = now - self.CLICK_WINDOW_SEC
        self._clicks = [t for t in self._clicks if t > cutoff]

        if len(self._clicks) >= self.CLICK_THRESHOLD:
            self._set(Emotion.HAPPY)
            self._clicks.clear()

    def on_chat(self, user_message: str) -> None:
        """分析聊天消息情绪。负面消息 → SAD，正面消息 → 可能回升。"""
        msg = user_message.lower()

        for kw in NEGATIVE_KEYWORDS:
            if kw in msg:
                self._set(Emotion.SAD)
                return

        for kw in POSITIVE_KEYWORDS:
            if kw in msg:
                if self._emotion == Emotion.SAD:
                    self._set(Emotion.NEUTRAL)
                return

    def reset(self) -> None:
        """手动重置为 NEUTRAL。"""
        self._set(Emotion.NEUTRAL)

    # ── 效果输出 ──────────────────────────────────────────────

    def pick_bubble(self, default_pool: list[str] | None = None) -> str:
        """根据当前情绪选择一条气泡文本。"""
        pools = {
            Emotion.NEUTRAL: NEUTRAL_BUBBLES,
            Emotion.HAPPY: HAPPY_BUBBLES,
            Emotion.SAD: SAD_BUBBLES,
        }
        pool = pools.get(self.current, NEUTRAL_BUBBLES)
        # 允许调用方传入回退池
        if default_pool and self.current == Emotion.NEUTRAL:
            pool = default_pool
        return random.choice(pool) if pool else ""

    def ai_context(self) -> str:
        """返回需要注入 AI 对话的情绪上下文，NEUTRAL 返回空字符串。"""
        return EMOTION_AI_CONTEXT.get(self.current, "")

    def weight_modifier(self) -> dict[str, float]:
        """返回状态权重修正系数（直接乘到现有权重上）。"""
        return dict(EMOTION_WEIGHT_MODIFIERS.get(self.current,
                          EMOTION_WEIGHT_MODIFIERS[Emotion.NEUTRAL]))

    def active_speech_scale(self) -> float:
        """主动说话概率缩放。SAD 时降低，HAPPY 时提高。"""
        scales = {Emotion.NEUTRAL: 1.0, Emotion.HAPPY: 1.5, Emotion.SAD: 0.3}
        return scales.get(self.current, 1.0)

    # ── 内部 ──────────────────────────────────────────────────

    def _set(self, emotion: Emotion) -> None:
        if emotion == self._emotion:
            self._set_at = time.time()  # 刷新持续时间
            return
        old = self._emotion
        self._emotion = emotion
        self._set_at = time.time()
        _log.info(f"[情绪] {old.value} → {emotion.value}")
