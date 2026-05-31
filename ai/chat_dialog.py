import os
import json
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QRectF
from PyQt6.QtGui import (
    QMouseEvent, QPainter, QPainterPath, QBrush, QColor,
    QLinearGradient, QPen,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QDialog, QMessageBox,
)


CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "DesktopPet", "config.json"
)

# ── 液态玻璃配色 ──
GLASS_BG = QColor(255, 255, 255, 165)          # 主体半透白
GLASS_GRADIENT_TOP = QColor(255, 255, 255, 200)
GLASS_GRADIENT_BOTTOM = QColor(240, 235, 225, 145)
GLASS_BORDER = QColor(255, 255, 255, 130)       # 亮边
GLASS_INNER_BORDER = QColor(255, 255, 255, 80)
GLASS_SHADOW = QColor(0, 0, 0, 30)
TEXT_COLOR = "#3D3028"
TEXT_MUTED = "#8A7B6E"
INPUT_BG = QColor(255, 255, 255, 160)
INPUT_BORDER = QColor(200, 188, 170, 180)
BTN_SEND_BG = QColor(200, 175, 130, 220)
BTN_SEND_HOVER = QColor(220, 195, 145, 235)
BTN_SEND_PRESSED = QColor(180, 155, 115, 240)
CLOSE_COLOR = QColor(160, 145, 130, 200)


def _load_pet_name():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("pet", "宠物")
    except Exception:
        return "宠物"


class _GlassTitleBar(QWidget):
    """液态玻璃标题栏：显示文字 + 关闭按钮，支持拖拽窗口。"""

    def __init__(self, pet_name: str, dialog: QWidget):
        super().__init__(dialog)
        self._dialog = dialog
        self._dragging = False
        self._offset = QPoint()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)

        title = QLabel(f"{pet_name} 在听~")
        title.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 14px; font-weight: bold;"
            "font-family: \"Microsoft YaHei\", \"PingFang SC\", sans-serif;"
            "background: transparent; border: none;"
        )
        layout.addWidget(title)
        layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                font-size: 16px; color: {TEXT_MUTED}; padding: 0;
            }}
            QPushButton:hover {{ color: #D06050; }}
        """)
        close_btn.clicked.connect(self._dialog.close)
        layout.addWidget(close_btn)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._offset = event.globalPosition().toPoint() - self._dialog.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            self._dialog.move(event.globalPosition().toPoint() - self._offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False
        super().mouseReleaseEvent(event)


class ChatDialog(QWidget):

    closed = pyqtSignal()
    _reply_ready = pyqtSignal(str, str)  # 跨线程：后台线程 → 主线程

    def __init__(self, parent=None, memory_manager=None, emotion_manager=None,
                 companion=None):
        super().__init__(parent)
        self.setWindowTitle("和宠物聊天")
        self.setMinimumSize(360, 440)
        self.resize(380, 500)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._bot = None
        self._memory = memory_manager
        self._emotion = emotion_manager
        self._companion = companion
        self._reply_ready.connect(self._on_chat_reply)
        self._setup_ui()
        self._init_bot()

    def _init_bot(self):
        from .doubao_api import DoubaoChat
        if not DoubaoChat.is_configured():
            self._show_api_key_setup()
        try:
            self._bot = DoubaoChat()
        except ValueError:
            self._bot = None

    def _show_api_key_setup(self):
        dlg = _ApiKeyDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            from .doubao_api import DoubaoChat
            DoubaoChat.save_key_to_config(dlg.api_key())
            # 重新初始化 bot
            try:
                self._bot = DoubaoChat()
                self._append_text("API Key 已保存，现在可以和我聊天啦~\n\n")
            except ValueError:
                pass
        else:
            self._append_text("提示: 未配置 API Key，无法使用 AI 对话。\n"
                            "请在 config.json 中设置 ark_api_key 字段。\n"
                            "获取 Key: https://console.volcengine.com/ark\n\n")

    def _setup_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 10, 16, 14)

        # ── 标题栏 ──
        pet_name = _load_pet_name()
        self._title_bar = _GlassTitleBar(pet_name, self)
        self._layout.addWidget(self._title_bar)

        # ── 聊天区域 ──
        self._chat_area = QTextEdit()
        self._chat_area.setReadOnly(True)
        self._chat_area.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                border: none;
                font-size: 14px;
                font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
                color: {TEXT_COLOR};
                selection-background-color: rgba(200, 175, 140, 100);
            }}
            QScrollBar:vertical {{
                background: rgba(0,0,0,0);
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(0,0,0,30);
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        self._layout.addWidget(self._chat_area, stretch=1)

        # ── 输入区域 ──
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 4, 0, 0)

        self._input = QLineEdit()
        self._input.setPlaceholderText("输入消息...")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba(255,255,255,150);
                border: 1.5px solid rgba(190,180,165,180);
                border-radius: 12px;
                padding: 7px 14px;
                font-size: 14px;
                font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
                color: {TEXT_COLOR};
            }}
            QLineEdit:focus {{
                border-color: rgba(170,150,120,220);
                background-color: rgba(255,255,255,200);
            }}
        """)
        self._input.returnPressed.connect(self._send)
        input_layout.addWidget(self._input, stretch=1)

        self._send_btn = QPushButton("发送")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setFixedHeight(34)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(200,175,130,200);
                border: none;
                border-radius: 12px;
                padding: 6px 20px;
                font-size: 14px;
                font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
                font-weight: bold;
                color: #5A4530;
            }}
            QPushButton:hover {{
                background-color: rgba(220,195,145,220);
            }}
            QPushButton:pressed {{
                background-color: rgba(180,155,115,230);
            }}
            QPushButton:disabled {{
                background-color: rgba(180,175,165,140);
                color: rgba(100,90,75,150);
            }}
        """)
        self._send_btn.clicked.connect(self._send)
        input_layout.addWidget(self._send_btn)

        self._layout.addLayout(input_layout)

        self._append_text(f"{pet_name}: 你好呀~ 想聊什么都可以跟我说哦~\n\n")

    # ── 液态玻璃背景绘制 ──
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        r = 20  # 圆角半径

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), r, r)

        # 外层阴影
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(QRectF(2, 2, w - 4, h - 4), r - 1, r - 1)
        painter.fillPath(shadow_path, QBrush(GLASS_SHADOW))

        # 主体玻璃渐变
        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, GLASS_GRADIENT_TOP)
        gradient.setColorAt(0.5, GLASS_BG)
        gradient.setColorAt(1.0, GLASS_GRADIENT_BOTTOM)
        painter.fillPath(path, QBrush(gradient))

        # 内发光边
        inner_path = QPainterPath()
        inner_path.addRoundedRect(QRectF(1.5, 1.5, w - 3, h - 3), r - 1, r - 1)
        pen = QPen(GLASS_INNER_BORDER, 1)
        painter.setPen(pen)
        painter.drawPath(inner_path)

        # 外边框
        outer_path = QPainterPath()
        outer_path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)
        pen = QPen(GLASS_BORDER, 1)
        painter.setPen(pen)
        painter.drawPath(outer_path)

        # 顶部高光
        highlight_path = QPainterPath()
        highlight_path.addRoundedRect(QRectF(8, 4, w * 0.4, 3), 1.5, 1.5)
        painter.fillPath(highlight_path, QBrush(QColor(255, 255, 255, 80)))

        painter.end()

    # ── 聊天气泡式输出 ──
    def _append_text(self, text):
        self._chat_area.moveCursor(self._chat_area.textCursor().MoveOperation.End)
        self._chat_area.insertPlainText(text)
        scrollbar = self._chat_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _send(self):
        text = self._input.text().strip()
        if not text:
            return
        if self._bot is None:
            self._show_api_key_setup()
        if self._bot is None:
            return

        self._input.clear()
        self._input.setEnabled(False)
        self._send_btn.setEnabled(False)

        self._append_text(f"你: {text}\n")
        self._append_text("... 正在思考...\n")

        QTimer.singleShot(50, lambda: self._do_chat(text))

    def _do_chat(self, text):
        # 情绪分析：用户消息 → 影响宠物情绪
        if self._emotion:
            self._emotion.on_chat(text)

        # 组装上下文（记忆 + 情绪 + 项目）
        msg = text
        prefixes = []
        if self._memory:
            ctx = self._memory.get_context_for_ai()
            if ctx:
                prefixes.append(f"[用户长期记忆]\n{ctx}")
        if self._emotion:
            em_ctx = self._emotion.ai_context()
            if em_ctx:
                prefixes.append(f"[宠物当前情绪]\n{em_ctx}")
        if self._companion:
            prj_ctx = self._companion.get_context_for_ai()
            if prj_ctx:
                prefixes.append(f"[用户长期项目]\n{prj_ctx}")
        if prefixes:
            msg = "\n\n".join(prefixes) + f"\n\n用户消息: {text}"

        # 后台线程调用 API，避免阻塞动画
        import threading
        threading.Thread(target=self._chat_thread, args=(text, msg), daemon=True).start()

    def _chat_thread(self, text, msg):
        """后台线程：调用 AI API，主线程更新 UI。"""
        import logging
        _log = logging.getLogger("chat")
        try:
            reply = self._bot.chat(msg)
        except Exception as e:
            _log.exception("AI 聊天请求失败")
            err = str(e).lower()
            if any(k in err for k in ("connection", "timeout", "timed out", "unreachable", "connecterror")):
                reply = "网络好像不太稳定... 检查一下网络再试试吧~"
            elif any(k in err for k in ("api", "key", "auth", "unauthorized", "forbidden")):
                reply = "API Key 好像有问题，检查一下 config.json 吧~"
            elif "not found" in err or "model" in err:
                reply = "模型好像不可用... 可能需要更新模型名称~"
            else:
                reply = f"唔... 出了点问题: {e}"
        finally:
            self._reply_ready.emit(text, reply)  # 跨线程信号 → 主线程 slot

    def _on_chat_reply(self, text, reply):
        """主线程：显示 AI 回复。"""
        if self._memory:
            self._memory.record_chat(text, reply)

        current = self._chat_area.toPlainText()
        current = current.replace("... 正在思考...\n", "")
        self._chat_area.setPlainText(current)

        self._append_text(f"宠物: {reply}\n\n")

        self._input.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._input.setFocus()


    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════
#  API Key 配置弹窗
# ═══════════════════════════════════════════════════════════════

class _ApiKeyDialog(QDialog):
    """首次使用时弹出，引导用户输入豆包 API Key。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置 API Key")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog
        )
        self.setFixedSize(440, 240)
        self.setStyleSheet("""
            _ApiKeyDialog {
                background: #FFFAF0;
                border: 2px solid #D4C8B0;
                border-radius: 14px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)

        title = QLabel("欢迎使用 AI 聊天功能")
        title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #5A4030; "
            "background: transparent; border: none;"
        )
        layout.addWidget(title)

        desc = QLabel(
            "宠物需要豆包 API Key 才能和你聊天。<br>"
            "在 <a href='https://console.volcengine.com/ark'>火山引擎 Ark 平台</a> "
            "注册并创建 API Key，粘贴到下方即可。"
        )
        desc.setOpenExternalLinks(True)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            "font-size: 12px; color: #7A6A58; background: transparent; border: none;"
        )
        layout.addWidget(desc)

        self._input = QLineEdit()
        self._input.setPlaceholderText("粘贴 API Key（以 ark- 开头）")
        self._input.setStyleSheet("""
            QLineEdit {
                padding: 8px 14px; border: 1.5px solid #D4C8B0;
                border-radius: 8px; font-size: 13px; background: #fff;
                color: #3A3228;
            }
            QLineEdit:focus { border-color: #B8A080; }
        """)
        layout.addWidget(self._input)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        skip = QPushButton("跳过")
        skip.clicked.connect(self.reject)
        skip.setStyleSheet("""
            QPushButton {
                padding: 6px 20px; border: 1px solid #d0ccc0;
                border-radius: 6px; background: #f5f3ee; font-size: 12px;
                color: #888;
            }
            QPushButton:hover { background: #e8e5dc; }
        """)
        btn_row.addWidget(skip)
        save = QPushButton("保存")
        save.clicked.connect(self._on_save)
        save.setStyleSheet("""
            QPushButton {
                padding: 6px 24px; border: none; border-radius: 6px;
                background: #d4a853; color: #fff; font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background: #c89830; }
        """)
        btn_row.addWidget(save)
        layout.addLayout(btn_row)

    def _on_save(self):
        key = self._input.text().strip()
        if not key:
            QMessageBox.warning(self, "提示", "请输入 API Key")
            return
        if not key.startswith("ark-"):
            reply = QMessageBox.question(
                self, "确认",
                "API Key 通常以 ark- 开头，你输入的似乎不是标准格式。\n确定保存吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def api_key(self) -> str:
        return self._input.text().strip()
