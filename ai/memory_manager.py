"""长期记忆管理模块。

纯数据层，不依赖任何其他项目模块。
使用 JSON 文件本地存储，跟踪用户行为习惯。
"""

import os
import json
import re
import datetime
from collections import Counter

DEFAULT_MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory.json")

# ── 可配置的中文关键词提取 ──
_KEYWORD_PATTERN = re.compile(r"[一-鿿]{2,}")
_STOP_WORDS = {"这个", "那个", "什么", "怎么", "一个", "一下", "可以", "没有",
               "不是", "现在", "已经", "还是", "不过", "但是", "因为", "所以",
               "如果", "虽然", "然后", "之后", "之前", "时候", "这个", "那个",
               "今天", "昨天", "明天", "知道", "觉得", "想要", "应该", "可能"}


class MemoryManager:
    """本地长期记忆管理器。

    存储结构::

        {
            "app_usage": { "VS Code": {"count": 10, "last_used": "..."}, ... },
            "daily_active": { "2026-05-25": {"start": "09:00", "end": "23:00"}, ... },
            "chat_keywords": ["Python", "Bug", ...],
            "late_nights": [{"date": "2026-05-25", "end": "02:30", "apps": [...]}, ...],
            "last_active": "2026-05-25T14:30:00"
        }
    """

    def __init__(self, filepath: str | None = None):
        self.filepath = filepath or DEFAULT_MEMORY_PATH
        self.data = self.load()

    # ── 读写磁盘 ──────────────────────────────────────────────

    def load(self) -> dict:
        """从 JSON 文件读取记忆。"""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return self._default()

    def save(self) -> None:
        """将记忆写入 JSON 文件。"""
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @staticmethod
    def _default() -> dict:
        return {
            "app_usage": {},
            "daily_active": {},
            "chat_keywords": [],
            "late_nights": [],
            "last_active": "",
        }

    # ── 公开更新 API ──────────────────────────────────────────

    def update(self, **kwargs) -> None:
        """批量更新顶层字段。"""
        self.data.update(kwargs)
        self.save()

    def record_app(self, app_name: str) -> None:
        """记录一次应用使用（来自窗口监听）。"""
        if not app_name:
            return
        usage = self.data.setdefault("app_usage", {})
        entry = usage.get(app_name)
        if entry is None:
            entry = {"count": 0, "last_used": ""}
            usage[app_name] = entry
        entry["count"] += 1
        entry["last_used"] = _now_iso()
        self.save()

    def record_active_time(self, start: str, end: str | None = None) -> None:
        """记录当日活跃时段。

        Args:
            start: 开始时间，如 "09:00"
            end: 结束时间，如 "23:00"（可选，不传则只记录开始）
        """
        today = _today()
        daily = self.data.setdefault("daily_active", {})
        entry = daily.get(today, {})
        if "start" not in entry or not entry["start"]:
            entry["start"] = start
        if end:
            entry["end"] = end
        daily[today] = entry
        self.data["last_active"] = _now_iso()
        self.save()

    def record_chat(self, message: str, reply: str = "") -> None:
        """从聊天消息中提取关键词并保存。

        对用户消息做简单分词 + 停用词过滤，
        提取 2 字以上中文词作为关键词。
        """
        words = _KEYWORD_PATTERN.findall(message)
        filtered = [w for w in words if w not in _STOP_WORDS]

        existing = self.data.get("chat_keywords", [])
        combined = existing + filtered

        # 保留频次前 30 的关键词
        counter = Counter(combined)
        self.data["chat_keywords"] = [w for w, _ in counter.most_common(30)]
        self.data["last_active"] = _now_iso()
        self.save()

    def record_late_night(self, apps: list[str] | None = None) -> None:
        """记录一次熬夜。

        自动取当天日期和当前时间。
        """
        now = datetime.datetime.now()
        if now.hour >= 6 and now.hour < 22:
            return  # 正常时间不记录

        today = _today()
        time_str = now.strftime("%H:%M")
        record = {"date": today, "end": time_str, "apps": apps or []}

        late_list = self.data.setdefault("late_nights", [])
        # 同一天已有记录则更新时间
        for entry in late_list:
            if entry.get("date") == today:
                entry["end"] = time_str
                if apps:
                    entry["apps"] = list(set(entry.get("apps", []) + apps))
                self.save()
                return

        late_list.append(record)
        if len(late_list) > 60:
            late_list[:] = late_list[-60:]
        self.save()

    # ── 查询 ──────────────────────────────────────────────────

    def top_apps(self, n: int = 5) -> list[tuple[str, int]]:
        """返回最常用的 n 个应用。"""
        usage = self.data.get("app_usage", {})
        sorted_apps = sorted(usage.items(),
                            key=lambda kv: kv[1].get("count", 0),
                            reverse=True)
        return [(name, info.get("count", 0)) for name, info in sorted_apps[:n]]

    def recent_keywords(self, n: int = 10) -> list[str]:
        """返回最近的聊天关键词。"""
        return self.data.get("chat_keywords", [])[:n]

    def late_night_count(self, days: int = 7) -> int:
        """返回最近 N 天的熬夜次数。"""
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        return sum(1 for r in self.data.get("late_nights", [])
                   if r.get("date", "") >= cutoff)

    def get_context_for_ai(self) -> str:
        """生成一段可供 AI 对话注入的记忆上下文文本。"""
        parts = []

        top = self.top_apps(5)
        if top:
            app_str = "、".join(f"{name}({cnt}次)" for name, cnt in top)
            parts.append(f"用户常用软件: {app_str}")

        kw = self.recent_keywords(10)
        if kw:
            parts.append(f"用户最近关注: {'、'.join(kw)}")

        late_count = self.late_night_count(7)
        if late_count > 0:
            parts.append(f"最近7天熬夜 {late_count} 次")

        daily = self.data.get("daily_active", {})
        today = _today()
        if today in daily and daily[today].get("start"):
            parts.append(f"今天 {daily[today]['start']} 开始使用电脑")

        last = self.data.get("last_active", "")
        if last:
            parts.append(f"上次活跃: {last}")

        return "。".join(parts) + "。" if parts else ""


# ── 工具函数 ─────────────────────────────────────────────────

def _today() -> str:
    return datetime.date.today().isoformat()


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")
