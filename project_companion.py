"""项目陪伴模式。

动态追踪用户电脑上所有软件的使用模式，自动识别长期项目，
检测已卸载软件并停止跟踪。生成陪伴对话 + 注入 AI 上下文。
"""

import os
import json
import random
import datetime
import ctypes
import logging
from ctypes import wintypes
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

_log = logging.getLogger("companion")


# ═══════════════════════════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════════════════════════

class CompanionConfig:
    # ── 项目识别 ──
    MIN_ACTIVE_DAYS = 3
    WINDOW_DAYS = 7
    MIN_DAILY_MINUTES = 10
    INACTIVE_DAYS = 5

    # ── 陪伴消息 ──
    MESSAGE_CHECK_MINUTES = 25
    MESSAGE_COOLDOWN_MINUTES = 90
    MILESTONE_DAYS = 7
    STREAK_DAYS = 3

    # ── 卸载检测 ──
    UNINSTALL_CHECK_MINUTES = 60     # 每小时检查一次卸载状态
    UNINSTALL_GRACE_DAYS = 14        # 卸载后保留数据天数，之后自动清理

    # ── 存储 ──
    DATA_FILE = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "DesktopPet", "project_data.json",
    )


# ═══════════════════════════════════════════════════════════════
#  Win32：获取进程可执行文件路径
# ═══════════════════════════════════════════════════════════════

_kernel32 = ctypes.windll.kernel32
_user32 = ctypes.windll.user32

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                              ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD

_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE

_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


def _get_process_path(hwnd: int) -> str:
    """从窗口句柄获取进程完整可执行文件路径。失败返回空字符串。"""
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    if not _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid)):
        return ""

    h = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""

    buf = (ctypes.c_wchar * 512)()
    size = wintypes.DWORD(512)
    ok = _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    _kernel32.CloseHandle(h)
    return buf[:size.value] if ok else ""


def _check_path_exists(path: str) -> bool:
    """检查路径对应的文件是否存在。"""
    return bool(path) and os.path.exists(path)


# ═══════════════════════════════════════════════════════════════
#  非项目软件排除名单 — 这些进程永远不算"项目"
# ═══════════════════════════════════════════════════════════════

_NON_PROJECT_PROCESSES: set[str] = {
    # 通讯 / 社交
    "wechat.exe", "weixin.exe", "微信.exe",
    "qq.exe", "tim.exe",
    "discord.exe", "slack.exe", "telegram.exe",
    "dingtalk.exe", "dingtalkmain.exe",
    "feishu.exe", "lark.exe",
    "teams.exe", "skype.exe",
    # 浏览器
    "chrome.exe", "msedge.exe", "firefox.exe",
    "iexplore.exe", "opera.exe", "brave.exe",
    "browser.exe",
    # 音乐 / 视频 / 娱乐
    "spotify.exe", "qqmusic.exe", "neteasecloudmusic.exe",
    "bilibili.exe", "qqlive.exe", "tencentvideo.exe",
    "iqiyi.exe", "youku.exe", "vlc.exe", "potplayer.exe",
    "steam.exe", "epicgameslauncher.exe",
    # 系统工具
    "explorer.exe", "taskmgr.exe", "cmd.exe", "powershell.exe",
    "windowsterminal.exe", "conhost.exe",
    "notepad.exe", "mspaint.exe", "snippingtool.exe",
    "calc.exe", "applicationframehost.exe", "systemsettings.exe",
    # 文件管理
    "winrar.exe", "7zfm.exe", "7zg.exe",
    "totalcmd64.exe", "everything.exe",
    "wiztree.exe", "spacesniffer.exe",
    # 截图 / 录屏
    "snipaste.exe", "sharex.exe", "obs64.exe",
    # 输入法
    "ctfmon.exe", "sogoucloud.exe", "sgtool.exe",
}


def _is_project_app(process_name: str) -> bool:
    """判断一个进程是否应被视为'项目软件'（非通讯/娱乐/系统工具）。"""
    if not process_name:
        return False
    return process_name.lower() not in _NON_PROJECT_PROCESSES


# ═══════════════════════════════════════════════════════════════
#  已知创意软件的领域描述（用于生成自然对话；未知软件用通用模板）
# ═══════════════════════════════════════════════════════════════

APP_DOMAINS: dict[str, str] = {
    "Premiere Pro":        "做视频",
    "After Effects":       "做特效/动画",
    "Unity":               "做游戏/3D",
    "VS Code":             "写代码",
    "Visual Studio Code":  "写代码",
    "Blender":             "做3D建模",
    "Photoshop":           "做设计/P图",
    "Illustrator":         "做矢量设计",
    "Figma":               "做UI设计",
    "IntelliJ IDEA":       "写Java",
    "PyCharm":             "写Python",
    "WebStorm":            "写前端",
    "GoLand":              "写Go",
}

# 常用进程名 → 友好显示名
_FRIENDLY_NAMES: dict[str, str] = {
    "Code.exe":       "VS Code",
    "devenv.exe":     "Visual Studio",
    "idea64.exe":     "IntelliJ IDEA",
    "pycharm64.exe":  "PyCharm",
    "webstorm64.exe": "WebStorm",
    "goland64.exe":   "GoLand",
    "Unity.exe":      "Unity",
    "blender.exe":    "Blender",
    "Photoshop.exe":  "Photoshop",
    "Illustrator.exe":"Illustrator",
    "AfterFX.exe":    "After Effects",
    "Figma.exe":      "Figma",
    "Code.cmd":       "VS Code",
}


def _friendly_name(process_name: str) -> str:
    """将进程名转为友好显示名。"""
    if not process_name:
        return "未知软件"
    # 先查映射表
    for key, val in _FRIENDLY_NAMES.items():
        if process_name.lower() == key.lower():
            return val
    # 去掉 .exe 后缀，首字母大写
    name = process_name
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name[:40]


# ═══════════════════════════════════════════════════════════════
#  陪伴消息模板
# ═══════════════════════════════════════════════════════════════

MILESTONE_MESSAGES = [
    "「{name}」这个项目已经做了{days}天了，还没结束吗？",
    "你和「{name}」已经相处{days}天了~",
    "注意休息哦，「{name}」不会跑掉的！",
    "这个「{name}」项目还要做多久呀？",
]

STREAK_MESSAGES = [
    "今天也在继续{domain}呀。",
    "你最近一直在{domain}呢~",
    "连续{streak}天都在{domain}，真厉害！",
    "每天都看到你在{domain}，加油！",
]

STREAK_GENERIC_MESSAGES = [
    "最近天天都在用「{name}」呢~",
    "你好像很喜欢用「{name}」？",
    "「{name}」已经连续用了{streak}天了！",
]

INACTIVE_MESSAGES = [
    "好久没看到你打开「{name}」了，项目还在吗？",
    "「{name}」是暂停了吗？",
    "之前常用的「{name}」最近怎么不用了？",
]

UNINSTALLED_MESSAGES = [
    "「{name}」好像被卸载了？这个项目结束了吗？",
    "注意到「{name}」已经不在了，项目告一段落了吧~",
]


# ═══════════════════════════════════════════════════════════════
#  ProjectCompanion
# ═══════════════════════════════════════════════════════════════

class ProjectCompanion(QObject):

    companion_message = pyqtSignal(str)

    def __init__(self, pet, config: CompanionConfig | None = None):
        super().__init__()
        self._pet = pet
        self._cfg = config or CompanionConfig()

        self._current_pname: str | None = None
        self._app_start: float | None = None

        # {process_name: {total_minutes, daily_minutes, exe_path, ...}}
        self._projects: dict = {}
        self._last_message_time: float | None = None

        # 卸载检测：轮询索引
        self._uninstall_check_idx = 0

        self._load()

        # 消息定时器
        self._msg_timer = QTimer(self)
        self._msg_timer.timeout.connect(self._check_messages)
        self._msg_timer.setInterval(self._cfg.MESSAGE_CHECK_MINUTES * 60 * 1000)

        # 时长累积
        self._duration_timer = QTimer(self)
        self._duration_timer.timeout.connect(self._tick_duration)
        self._duration_timer.setInterval(60_000)

        # 卸载检测
        self._uninstall_timer = QTimer(self)
        self._uninstall_timer.timeout.connect(self._check_uninstalled)
        self._uninstall_timer.setInterval(self._cfg.UNINSTALL_CHECK_MINUTES * 60 * 1000)

    # ── 公开 API ──────────────────────────────────────────────

    def start(self):
        self._msg_timer.start()
        self._duration_timer.start()
        self._uninstall_timer.start()
        _log.info(f"[陪伴] 已启动 (追踪 {len(self._projects)} 个软件)")

    def stop(self):
        self._msg_timer.stop()
        self._duration_timer.stop()
        self._uninstall_timer.stop()
        self._end_session()
        self._save()

    def on_window_change(self, process_name: str | None, hwnd: int = 0):
        """窗口切换时调用。

        Args:
            process_name: 进程名（如 Code.exe），不传 main.py 的 app_name
            hwnd: 窗口句柄，用于获取 exe 路径（仅首次发现时需要）
        """
        now = self._now_sec()

        # 结算上一个
        if self._current_pname and self._app_start:
            elapsed = (now - self._app_start) / 60.0
            self._add_minutes(self._current_pname, elapsed)

        # 开始新计时
        if process_name:
            self._current_pname = process_name
            self._app_start = now
            # 首次发现 → 获取 exe 路径
            if process_name not in self._projects:
                self._discover(process_name, hwnd)
        else:
            self._current_pname = None
            self._app_start = None

    def get_context_for_ai(self) -> str:
        today = datetime.date.today()

        # ── 活跃项目 ──
        active = self.get_active_projects()
        active_parts = []
        for name, info in sorted(active, key=lambda x: -x[1]["active_days"]):
            days = info["active_days"]
            hours = info["total_minutes"] / 60
            show = _friendly_name(name)
            domain = APP_DOMAINS.get(show, "")
            domain_str = f"({domain})" if domain else ""
            active_parts.append(f"「{show}」{domain_str}已持续{days}天，累计{hours:.0f}小时")

        # ── 搁置项目（≥INACTIVE_DAYS 天未打开，且曾有过实质性使用）──
        dormant_parts = []
        for name, info in self._projects.items():
            if info.get("uninstalled"):
                continue
            if not _is_project_app(name):
                continue
            last = info.get("last_active_date", "")
            if not last:
                continue
            days_since = (today - datetime.date.fromisoformat(last)).days
            if days_since < self._cfg.INACTIVE_DAYS:
                continue
            # 累计 < 1 小时的不注入
            if info["total_minutes"] < 60:
                continue
            # 必须曾经是"长期项目"：历史上至少 MIN_ACTIVE_DAYS 天活跃过
            # （过滤掉只看了一次电影、偶尔开了一次软件的情况）
            if self._count_lifetime_active_days(info) < self._cfg.MIN_ACTIVE_DAYS:
                continue

            show = _friendly_name(name)
            hours = info["total_minutes"] / 60
            dormant_parts.append(f"「{show}」搁置{days_since}天，曾累计{hours:.0f}小时")

        # ── 拼接 ──
        result_parts = []
        if active_parts:
            result_parts.append("活跃项目: " + "；".join(active_parts))
        if dormant_parts:
            result_parts.append("搁置项目: " + "；".join(dormant_parts[:5]))
        return "。".join(result_parts) if result_parts else ""

    def get_active_projects(self) -> list[tuple[str, dict]]:
        today = datetime.date.today()
        result = []
        for name, info in self._projects.items():
            if info.get("uninstalled"):
                continue
            if not _is_project_app(name):
                continue
            active_days = self._count_active_days(info, today)
            if active_days >= self._cfg.MIN_ACTIVE_DAYS:
                info["active_days"] = active_days
                result.append((name, info))
        result.sort(key=lambda x: -x[1]["active_days"])
        return result

    def get_all_projects(self) -> dict:
        """返回所有追踪数据（供外部查看）。"""
        return dict(self._projects)

    # ── 软件发现 ──────────────────────────────────────────────

    def _discover(self, process_name: str, hwnd: int):
        """首次发现新软件：记录 exe 路径。"""
        exe_path = ""
        if hwnd:
            exe_path = _get_process_path(hwnd)
            if exe_path:
                _log.info(f"[陪伴] 发现新软件: {_friendly_name(process_name)} → {exe_path}")
            else:
                _log.info(f"[陪伴] 发现新软件: {_friendly_name(process_name)} (无法获取路径)")
        else:
            _log.info(f"[陪伴] 发现新软件: {_friendly_name(process_name)} (无窗口句柄)")

        if process_name not in self._projects:
            self._projects[process_name] = self._new_project(exe_path)

    # ── 卸载检测 ──────────────────────────────────────────────

    def _check_uninstalled(self):
        """轮询检查：逐个软件验证 exe 是否还存在。"""
        names = list(self._projects.keys())
        if not names:
            return
        idx = self._uninstall_check_idx % len(names)
        self._uninstall_check_idx += 1
        pname = names[idx]
        info = self._projects[pname]

        # 已经标记卸载的跳过
        if info.get("uninstalled"):
            return

        exe_path = info.get("exe_path", "")
        if not exe_path:
            return  # 没有路径则无法判断

        if not _check_path_exists(exe_path):
            info["uninstalled"] = True
            info["uninstalled_date"] = datetime.date.today().isoformat()
            show = _friendly_name(pname)
            _log.info(f"[陪伴] 检测到已卸载: {show} ({exe_path})")
            self._save()

            # 触发卸载消息
            msg = random.choice(UNINSTALLED_MESSAGES).format(name=show)
            self._pet.show_bubble(msg)
            self.companion_message.emit(msg)

    def _prune_old_uninstalled(self):
        """清理超过保留期的卸载数据。"""
        today = datetime.date.today()
        to_remove = []
        for name, info in self._projects.items():
            if info.get("uninstalled"):
                d = info.get("uninstalled_date", "")
                try:
                    days = (today - datetime.date.fromisoformat(d)).days
                except (ValueError, TypeError):
                    days = 0
                if days > self._cfg.UNINSTALL_GRACE_DAYS:
                    to_remove.append(name)

        for name in to_remove:
            show = _friendly_name(name)
            _log.info(f"[陪伴] 清理过期卸载数据: {show}")
            del self._projects[name]

        if to_remove:
            self._save()

    def _prune_rare_software(self):
        """清理极少使用且长期未打开的软件记录（<3 分钟 + 90 天未打开）。"""
        today = datetime.date.today()
        to_remove = []
        for name, info in self._projects.items():
            if info.get("uninstalled"):
                continue  # 已卸载的走另一个清理逻辑
            total = info.get("total_minutes", 0)
            last = info.get("last_active_date", "")
            try:
                days_since = (today - datetime.date.fromisoformat(last)).days
            except (ValueError, TypeError):
                days_since = 999
            if total < 3 and days_since > 90:
                to_remove.append(name)

        for name in to_remove:
            show = _friendly_name(name)
            _log.info(f"[陪伴] 清理低频数据: {show} ({self._projects[name].get('total_minutes', 0)}分钟)")
            del self._projects[name]

        if to_remove:
            self._save()

    # ── 时长累积 ──────────────────────────────────────────────

    def _tick_duration(self):
        if self._current_pname and self._app_start:
            elapsed = (self._now_sec() - self._app_start) / 60.0
            if elapsed >= 1.0:
                self._add_minutes(self._current_pname, elapsed)
                self._app_start = self._now_sec()

    def _end_session(self):
        if self._current_pname and self._app_start:
            elapsed = (self._now_sec() - self._app_start) / 60.0
            self._add_minutes(self._current_pname, elapsed)
            self._current_pname = None
            self._app_start = None

    def _add_minutes(self, pname: str, minutes: float):
        if pname not in self._projects:
            self._projects[pname] = self._new_project()
        p = self._projects[pname]
        p["total_minutes"] += minutes
        today = datetime.date.today().isoformat()
        p["daily_minutes"][today] = p["daily_minutes"].get(today, 0) + minutes
        p["last_active_date"] = today
        if p["first_seen_date"] is None:
            p["first_seen_date"] = today
        self._update_streak(pname)
        self._save()

    # ── 陪伴消息 ──────────────────────────────────────────────

    def _check_messages(self):
        now_sec = self._now_sec()
        if self._last_message_time:
            if now_sec - self._last_message_time < self._cfg.MESSAGE_COOLDOWN_MINUTES * 60:
                return

        # 顺便清理过期卸载数据 + 低频软件
        self._prune_old_uninstalled()
        self._prune_rare_software()

        msg = self._generate_message()
        if msg:
            self._pet.show_bubble(msg)
            self.companion_message.emit(msg)
            self._last_message_time = now_sec
            _log.info(f"[陪伴] {msg}")

    def _generate_message(self) -> str | None:
        today = datetime.date.today()
        candidates: list[tuple[float, str]] = []

        for pname, info in self._projects.items():
            if info.get("uninstalled"):
                continue
            if not _is_project_app(pname):
                continue

            active_days = self._count_active_days(info, today)
            if active_days < self._cfg.MIN_ACTIVE_DAYS:
                continue

            streak = info.get("current_streak", 0)
            show = _friendly_name(pname)
            domain = APP_DOMAINS.get(show, "")
            total_hours = info["total_minutes"] / 60

            # 规则1：里程碑
            if active_days >= self._cfg.MILESTONE_DAYS:
                msg = random.choice(MILESTONE_MESSAGES).format(
                    name=show, domain=domain or f"使用{show}",
                    days=active_days, hours=f"{total_hours:.0f}",
                )
                candidates.append((0.6, msg))

            # 规则2：连续活跃
            if streak >= self._cfg.STREAK_DAYS:
                if domain:
                    msg = random.choice(STREAK_MESSAGES).format(
                        name=show, domain=domain, streak=streak,
                    )
                else:
                    msg = random.choice(STREAK_GENERIC_MESSAGES).format(
                        name=show, streak=streak,
                    )
                candidates.append((0.5, msg))

            # 规则3：长时间未打开
            days_since = None
            last = info.get("last_active_date", "")
            if last:
                try:
                    days_since = (today - datetime.date.fromisoformat(last)).days
                except (ValueError, TypeError):
                    pass
            if days_since is not None and days_since >= self._cfg.INACTIVE_DAYS:
                msg = random.choice(INACTIVE_MESSAGES).format(
                    name=show, domain=domain or f"使用{show}",
                )
                candidates.append((0.4, msg))

        if not candidates:
            return None

        total_w = sum(w for w, _ in candidates)
        r = random.uniform(0, total_w)
        acc = 0
        for w, msg in candidates:
            acc += w
            if r <= acc:
                return msg
        return candidates[-1][1]

    # ── 数据存取 ──────────────────────────────────────────────

    def _load(self):
        try:
            with open(self._cfg.DATA_FILE, "r", encoding="utf-8") as f:
                self._projects = json.load(f)
            # 将旧格式（无 exe_path）升级
            for p in self._projects.values():
                p.setdefault("exe_path", "")
                p.setdefault("uninstalled", False)
                p.setdefault("uninstalled_date", "")
            _log.info(f"[陪伴] 已加载 ({len(self._projects)} 个软件)")
        except (FileNotFoundError, json.JSONDecodeError):
            self._projects = {}

    def _save(self):
        try:
            with open(self._cfg.DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._projects, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ── 工具 ──────────────────────────────────────────────────

    @staticmethod
    def _new_project(exe_path: str = "") -> dict:
        return {
            "active_days": 0,
            "total_minutes": 0,
            "daily_minutes": {},
            "last_active_date": None,
            "first_seen_date": None,
            "current_streak": 0,
            "longest_streak": 0,
            "exe_path": exe_path,
            "uninstalled": False,
            "uninstalled_date": "",
        }

    def _count_lifetime_active_days(self, info: dict) -> int:
        """统计历史上有多少天活跃 >= MIN_DAILY_MINUTES（全量，不限窗口）。"""
        return sum(
            1 for m in info.get("daily_minutes", {}).values()
            if m >= self._cfg.MIN_DAILY_MINUTES
        )

    def _count_active_days(self, info: dict, today: datetime.date) -> int:
        count = 0
        for i in range(self._cfg.WINDOW_DAYS):
            day = (today - datetime.timedelta(days=i)).isoformat()
            if info.get("daily_minutes", {}).get(day, 0) >= self._cfg.MIN_DAILY_MINUTES:
                count += 1
        return count

    def _update_streak(self, pname: str):
        today = datetime.date.today()
        p = self._projects[pname]
        daily = p.get("daily_minutes", {})
        streak = 0
        for i in range(365):
            day = (today - datetime.timedelta(days=i)).isoformat()
            if daily.get(day, 0) >= self._cfg.MIN_DAILY_MINUTES:
                streak += 1
            else:
                break
        p["current_streak"] = streak
        if streak > p.get("longest_streak", 0):
            p["longest_streak"] = streak

    @staticmethod
    def _now_sec() -> float:
        return datetime.datetime.now().timestamp()
