import sys
import os
import json
import datetime
import logging
from logging.handlers import RotatingFileHandler
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QCursor, QPainter, QColor, QBrush, QPen, QPixmap, QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

# ── 日志配置（必须在所有模块导入前设置）──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-18s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        RotatingFileHandler(
            os.path.join(os.path.dirname(__file__), "pet.log"),
            encoding="utf-8",
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=2,
        ),
        logging.StreamHandler(sys.stdout),
    ],
)

_log = logging.getLogger("main")

from pet_window import PetWindow
from pet_selector import PetSelector, discover_pets
from window_monitor import WindowMonitor, WindowInfo
from ai.memory_manager import MemoryManager
from ai.emotion_state import EmotionManager
from event_system import EventSystem
from desktop_attachment import DesktopAttachment
from desktop_marks import DeskMarkManager
from project_companion import ProjectCompanion
from music_visualizer import MusicVisualizer
from weather_service import get_weather, get_weather_mood
from proactive_chat import ProactiveChat
from settings_dialog import SettingsDialog


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
CONFIG_EXAMPLE_PATH = os.path.join(os.path.dirname(__file__), "config.example.json")
RESOURCES_DIR = os.path.join(os.path.dirname(__file__), "resources")

# 首次运行：从模板复制配置文件（不携带开发者的真实 key）
if not os.path.exists(CONFIG_PATH) and os.path.exists(CONFIG_EXAMPLE_PATH):
    import shutil
    shutil.copy2(CONFIG_EXAMPLE_PATH, CONFIG_PATH)
    _log.info("[配置] 已从 config.example.json 生成初始配置")

# ── 应用关键词 → 宠物台词 ──────────────────────────────────────

APP_MESSAGES: dict[str, list[str]] = {
    "Premiere Pro": [
        "今天继续剪视频吗？",
        "PR 又卡了吗？",
        "渲染的时候休息一下吧~",
    ],
    "After Effects": [
        "做特效好厉害！",
        "AE 工程又崩了吗...",
    ],
    "Photoshop": [
        "P 图大师上线！",
        "这个图层好难找...",
    ],
    "VS Code": [
        "又在写代码呀~",
        "Bug 都修完了吗？",
    ],
    "Terminal": [
        "命令行操作中...",
        "小心 rm -rf 哦！",
    ],
    "WeChat": [
        "有人发消息来了吗？",
        "在和朋友聊天吗~",
    ],
    "Spotify": [
        "音乐时间！",
    ],
    "QQMusic": [
        "听歌放松一下吧~",
    ],
    "bilibili": [
        "在看视频摸鱼吗！",
    ],
    "Steam": [
        "打游戏不叫我！",
    ],
    "explorer": [
        "在找什么文件呢？",
    ],
    "Unity": [
        "游戏做得怎么样了？",
        "Unity 又报错了？",
    ],
    "Blender": [
        "建模建得怎么样了？",
        "这个模型好精细呀！",
    ],
}

APP_KEYWORDS: dict[str, list[str]] = {
    "VS Code":       ["Visual Studio Code", "Code"],
    "Photoshop":     ["Photoshop"],
    "Premiere Pro":  ["Premiere Pro", "Adobe Premiere Pro"],
    "After Effects": ["After Effects", "AfterFX"],
    "Terminal":      ["Terminal", "Windows Terminal", "cmd"],
    "WeChat":        ["微信", "WeChat"],
    "QQMusic":       ["QQMusic", "QQ音乐"],
    "bilibili":      ["bilibili", "哔哩哔哩"],
    "Spotify":       ["Spotify"],
    "Steam":         ["Steam"],
    "explorer":      ["文件资源管理器"],
    "Unity":         ["Unity", "Unity Editor"],
    "Blender":       ["Blender"],
}


def match_app(info: WindowInfo) -> str | None:
    haystack = (info.title + " " + info.process_name).lower()
    for app_name, keywords in APP_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in haystack:
                return app_name
    return None


def on_window_changed(pet: PetWindow, old: WindowInfo, new: WindowInfo) -> str | None:
    app = match_app(new)
    app_str = f" ({app})" if app else ""
    _log.info(f"窗口切换: {old.process_name or '(桌面)'} → {new.process_name}{app_str}")
    if new.title:
        _log.debug(f"  标题: {new.title}")
    if app and app in APP_MESSAGES:
        import random
        pet.show_bubble(random.choice(APP_MESSAGES[app]))
    return app  # 返回匹配到的应用名，供外部记录


# ── 配置持久化 ────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def get_initial_pet_path() -> str | None:
    """根据配置返回上次选择的宠物路径。"""
    cfg = load_config()
    pet_name = cfg.get("pet")
    resources_path = cfg.get("resources_path")
    if pet_name is not None and pet_name != "默认猫咪" and resources_path:
        return resources_path
    return None


def save_pet_selection(info: dict) -> None:
    cfg = load_config()
    cfg["pet"] = info["name"]
    cfg["resources_path"] = info["path"]
    save_config(cfg)


# ── 托盘图标 ────────────────────────────────────────────────

def _make_tray_icon() -> QIcon:
    """用 QPainter 画一个 32x32 的小猫头图标。"""
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    # 脸
    p.setBrush(QBrush(QColor(255, 210, 140)))
    p.drawEllipse(4, 8, 24, 22)
    # 耳朵
    p.setBrush(QBrush(QColor(255, 160, 80)))
    p.drawPolygon(QPoint(8, 10), QPoint(13, 1), QPoint(16, 9))
    p.drawPolygon(QPoint(16, 9), QPoint(19, 1), QPoint(24, 10))
    # 眼睛
    p.setBrush(QBrush(QColor(50, 30, 20)))
    p.drawEllipse(11, 16, 4, 5)
    p.drawEllipse(18, 16, 4, 5)
    # 鼻子
    p.setBrush(QBrush(QColor(255, 120, 120)))
    p.drawEllipse(15, 22, 3, 2)
    # 嘴
    pen = QPen(QColor(80, 50, 30), 1)
    p.setPen(pen)
    p.drawLine(16, 24, 13, 26)
    p.drawLine(16, 24, 19, 26)
    p.end()
    return QIcon(pm)


def _on_tray_activate(reason, pet: PetWindow):
    """双击托盘图标 → 显示/隐藏宠物。"""
    if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
        _toggle_pet(pet)


def _toggle_pet(pet: PetWindow):
    if pet.isVisible():
        pet.hide()
    else:
        pet.show()


# ── 开机自启动 ──────────────────────────────────────────────

def _get_startup_vbs_path() -> str:
    """获取开机启动 VBS 脚本的路径。"""
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
    )
    return os.path.join(startup_dir, "桌面宠物.vbs")


def _set_auto_start(enabled: bool) -> bool:
    """启用/禁用开机自启动。返回是否成功。"""
    vbs_path = _get_startup_vbs_path()
    if enabled:
        python_exe = sys.executable
        main_py = os.path.abspath(__file__)
        work_dir = os.path.dirname(main_py)
        vbs_content = (
            f'CreateObject("WScript.Shell").Run '
            f'"""{python_exe}" "{main_py}""", 0, False\n'
            f"' WorkingDirectory: {work_dir}\n"
        )
        try:
            os.makedirs(os.path.dirname(vbs_path), exist_ok=True)
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write(vbs_content)
            _log.info(f"开机自启动已启用 → {vbs_path}")
            return True
        except OSError as e:
            _log.warning(f"启用自启动失败: {e}")
            return False
    else:
        try:
            if os.path.exists(vbs_path):
                os.remove(vbs_path)
                _log.info("开机自启动已禁用")
            return True
        except OSError as e:
            _log.warning(f"禁用自启动失败: {e}")
            return False


def _is_auto_start_enabled() -> bool:
    """检查自启动是否已启用。"""
    return os.path.exists(_get_startup_vbs_path())


def _check_first_run_auto_start():
    """首次运行：询问是否开机自启动。"""
    cfg = load_config()
    if "auto_start" in cfg:
        return  # 已经问过了

    from PyQt6.QtWidgets import QMessageBox
    reply = QMessageBox.question(
        None,
        "桌面宠物",
        "要设置开机自动启动吗？\n\n"
        "启用后，每次开机宠物都会自动出现陪你。\n"
        "之后可以在托盘菜单中随时更改。",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    enabled = (reply == QMessageBox.StandardButton.Yes)
    _set_auto_start(enabled)
    cfg["auto_start"] = enabled
    save_config(cfg)


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)

    # ── 长期记忆 ──
    memory = MemoryManager()
    memory.record_active_time(datetime.datetime.now().strftime("%H:%M"))

    # ── 情绪管理 ──
    emotion = EmotionManager()

    # ── 创建宠物窗口 ──
    initial_path = get_initial_pet_path()

    pet = PetWindow(initial_path)
    pet.set_emotion_manager(emotion)
    pet.show()

    # ── 首次运行询问（先隐藏宠物，避免遮挡对话框）──
    pet.hide()
    _check_first_run_auto_start()
    pet.show()

    # ── 初始位置：左下角 ──
    screen = QApplication.primaryScreen()
    geo = screen.availableGeometry()
    pet.move(geo.left() + 20, geo.bottom() - pet.height() - 10)

    # ── 启动冻结：有输入时不移动，空闲 5 分钟后解冻 ──
    pet.freeze()
    _unfreeze_checked = False

    def _check_unfreeze():
        nonlocal _unfreeze_checked
        if _unfreeze_checked:
            return
        from event_system import get_idle_seconds
        if get_idle_seconds() >= 300:  # 5 分钟无操作
            _unfreeze_checked = True
            _unfreeze_timer.stop()
            pet.unfreeze()

    _unfreeze_timer = QTimer(pet)
    _unfreeze_timer.timeout.connect(_check_unfreeze)
    _unfreeze_timer.start(3000)  # 每 3 秒检查一次

    # ── 事件系统 ──
    events = EventSystem(pet, memory)

    # ── 桌面依附 ──
    attachment = DesktopAttachment(pet)

    # ── 桌面痕迹 ──
    marks = DeskMarkManager(pet)

    # ── 项目陪伴 ──
    companion = ProjectCompanion(pet)

    # ── 音乐可视化 ──
    music_viz = MusicVisualizer(pet)

    if initial_path:
        _log.info(f"上次选择的宠物: {os.path.basename(initial_path)}")
    else:
        _log.info("使用默认猫咪")

    # ── 创建选择器 ──
    selector = PetSelector(RESOURCES_DIR)

    def show_selector():
        """在鼠标位置附近打开选择窗口。"""
        pos = QCursor.pos()
        selector.show_at(pos)

    pet.switch_requested.connect(show_selector)

    # ── 双击开启对话 ──
    chat_dialog = None

    def show_chat():
        nonlocal chat_dialog
        if chat_dialog is not None and chat_dialog.isVisible():
            chat_dialog.raise_()
            chat_dialog.activateWindow()
            return
        from ai.chat_dialog import ChatDialog
        chat_dialog = ChatDialog(memory_manager=memory, emotion_manager=emotion,
                                 companion=companion)
        chat_dialog.destroyed.connect(lambda: _clear_chat_ref())
        # 定位到屏幕左下角
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        chat_dialog.move(geo.left() + 30,
                         geo.bottom() - chat_dialog.height() - 30)
        chat_dialog.show()

    def _clear_chat_ref():
        nonlocal chat_dialog
        chat_dialog = None

    pet.chat_requested.connect(show_chat)

    def on_pet_selected(info: dict) -> None:
        _log.info(f"更换宠物: {info['name']} (type={info['type']})")
        pet.switch_pet(info["path"])
        save_pet_selection(info)
        selector.hide()
        if info["path"]:
            pet.show_bubble(f"我是{info['name']}~")
        else:
            pet.show_bubble("喵~ 还是本喵最可爱！")

    selector.pet_selected.connect(on_pet_selected)

    def on_pet_deleted(deleted_path: str) -> None:
        cfg = load_config()
        if cfg.get("resources_path") == deleted_path:
            cfg.pop("pet", None)
            cfg.pop("resources_path", None)
            save_config(cfg)
        _log.info(f"删除宠物: {os.path.basename(deleted_path) if deleted_path else '(内置)'}")
        pet.show_bubble("有宠物离开了...")

    selector.pet_deleted.connect(on_pet_deleted)

    # 高亮当前选中的卡片
    if initial_path:
        selector.set_current(initial_path)
    else:
        selector.set_current(None)

    # ── 窗口监听（含记忆记录）──
    def _on_window_changed_with_memory(pet, old, new, mem):
        app = on_window_changed(pet, old, new)
        events.touch()  # 窗口切换 = 用户活跃
        marks.clear_all()  # 用户活跃时清除桌面痕迹
        companion.on_window_change(new.process_name, new.hwnd)  # 追踪所有软件
        if app:
            mem.record_app(app)
            now = datetime.datetime.now()
            if now.hour >= 23 or now.hour < 6:
                mem.record_late_night([app])

    # ── 窗口监听 ──
    monitor = WindowMonitor(interval_ms=500)
    monitor.window_changed.connect(
        lambda old, new: _on_window_changed_with_memory(pet, old, new, memory)
    )
    monitor.start()
    _log.info(f"窗口监听已启动 (轮询间隔: 500ms)")
    info = monitor.current
    _log.info(f"当前窗口: {info.process_name or '(桌面)'} - {info.title}")

    events.start()
    attachment.start()
    marks.start()
    companion.start()
    music_viz.start()

    # ── 主动说话 ──
    proactive = ProactiveChat(pet, memory_manager=memory, emotion_manager=emotion,
                              companion=companion, interval_minutes=20)
    proactive.start()

    # ── 全屏检测：前台窗口覆盖整个屏幕时自动隐藏宠物 ──
    _was_fullscreen = False

    def _check_fullscreen():
        nonlocal _was_fullscreen
        fg = _foreground_hwnd()
        wr = _window_rect(fg)
        if wr is None:
            if _was_fullscreen:
                _was_fullscreen = False
                pet.show()
                TickManager.instance().resume_all()
            return

        is_fs = False
        for screen in QApplication.screens():
            sg = screen.geometry()
            w_ok = abs(wr.width() - sg.width()) <= 8
            h_ok = abs(wr.height() - sg.height()) <= 8
            x_ok = abs(wr.x() - sg.x()) <= 4
            y_ok = abs(wr.y() - sg.y()) <= 4
            if w_ok and h_ok and x_ok and y_ok:
                is_fs = True
                break

        if is_fs and not _was_fullscreen:
            _was_fullscreen = True
            pet.hide()
            TickManager.instance().pause_all()
            _log.info("全屏模式：宠物已隐藏")
        elif not is_fs and _was_fullscreen:
            _was_fullscreen = False
            pet.show()
            TickManager.instance().resume_all()
            _log.info("退出全屏：宠物已显示")

    from tick_manager import TickManager
    from desktop_attachment import _foreground_hwnd, _window_rect
    TickManager.instance().register("fullscreen", _check_fullscreen, 800)

    # ── 自动天气（后台线程查询，避免阻塞动画）──
    import random as _weather_rnd
    import threading
    _weather_checked = False

    def _check_weather_auto():
        nonlocal _weather_checked
        delay = (30 + _weather_rnd.randint(-10, 10)) * 60_000 if _weather_checked else 120_000
        _weather_checked = True
        QTimer.singleShot(delay, _check_weather_auto)

        def _query():
            info = get_weather()
            if info:
                msg, _ = get_weather_mood(info)

                def _show():
                    pet.show_bubble(msg)
                    _log.info(f"天气心情: {msg}")

                QTimer.singleShot(0, _show)

        threading.Thread(target=_query, daemon=True).start()

    QTimer.singleShot(120_000, _check_weather_auto)  # 2 分钟后首次

    # ── 系统托盘 ──
    tray = QSystemTrayIcon()
    tray.setIcon(_make_tray_icon())
    tray.setToolTip("桌面宠物")
    tray.activated.connect(lambda reason: _on_tray_activate(reason, pet))

    tray_menu = QMenu()
    show_action = tray_menu.addAction("显示/隐藏宠物")
    show_action.triggered.connect(lambda: _toggle_pet(pet))

    def show_selector_from_tray():
        pos = QCursor.pos()
        selector.show_at(pos)
    switch_action = tray_menu.addAction("更换宠物...")
    switch_action.triggered.connect(show_selector_from_tray)

    auto_start_action = tray_menu.addAction("开机自启动")
    auto_start_action.setCheckable(True)
    auto_start_action.setChecked(_is_auto_start_enabled())
    auto_start_action.triggered.connect(
        lambda checked: _set_auto_start(checked)
    )

    glow_enabled = load_config().get("music_glow", True)

    glow_action = tray_menu.addAction("音乐光环")
    glow_action.setCheckable(True)
    glow_action.setChecked(glow_enabled)
    music_viz.set_glow_enabled(glow_enabled)

    def toggle_glow(checked):
        music_viz.set_glow_enabled(checked)
        cfg = load_config()
        cfg["music_glow"] = checked
        save_config(cfg)

    glow_action.triggered.connect(toggle_glow)

    def _apply_settings(cfg, viz, pr_chat):
        """应用配置面板的更改。"""
        if "music_glow" in cfg:
            viz.set_glow_enabled(cfg["music_glow"])
        if "proactive_interval" in cfg:
            pr_chat.set_interval(cfg["proactive_interval"])

    _settings_dlg = None

    def show_settings():
        nonlocal _settings_dlg
        if _settings_dlg is not None:
            _settings_dlg.close()
        _settings_dlg = SettingsDialog(on_saved=lambda cfg: _apply_settings(cfg, music_viz, proactive))
        _settings_dlg.destroyed.connect(lambda: _clear_settings_ref())
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        _settings_dlg.move(geo.left() + 80, geo.top() + 80)
        _settings_dlg.show()

    def _clear_settings_ref():
        nonlocal _settings_dlg
        _settings_dlg = None

    settings_action = tray_menu.addAction("设置...")
    settings_action.triggered.connect(show_settings)

    tray_menu.addSeparator()

    def quit_app():
        tray.hide()
        events.stop()
        attachment.stop()
        marks.stop()
        companion.stop()
        music_viz.stop()
        proactive.stop()
        monitor.stop()
        companion._end_session()
        QApplication.instance().quit()

    quit_action = tray_menu.addAction("退出")
    quit_action.triggered.connect(quit_app)
    tray.setContextMenu(tray_menu)
    tray.show()

    # 重写宠物右键"退出"为隐藏到托盘
    _orig_menu = pet.contextMenuEvent

    def _tray_context_menu(event):
        menu = QMenu(pet)
        switch = menu.addAction("更换宠物...")
        switch.triggered.connect(pet.switch_requested.emit)
        menu.addSeparator()
        hide = menu.addAction("隐藏到托盘")
        hide.triggered.connect(pet.hide)
        quit_act = menu.addAction("退出")
        quit_act.triggered.connect(quit_app)
        menu.exec(event.globalPos())

    pet.contextMenuEvent = _tray_context_menu

    _log.info("系统托盘已启动")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
