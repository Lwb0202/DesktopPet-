"""配置面板 — 管理 API Key、自动启动、音乐光环等设置。"""

import os
import json
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter, QPainterPath, QBrush, QColor, QLinearGradient, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QComboBox,
)

CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "DesktopPet", "config.json"
)


# ── 配色 ──
BG = QColor(255, 255, 255, 190)
BORDER = QColor(220, 210, 190, 150)
TEXT = "#4A3B2F"
MUTED = "#8A7A6A"
ACCENT = "#C8A050"


class SettingsDialog(QWidget):
    """独立配置窗口，液态玻璃风格。"""

    def __init__(self, parent=None, on_saved=None):
        super().__init__(parent)
        self._on_saved = on_saved
        self._cfg = self._load()

        self.setWindowTitle("设置")
        self.setMinimumSize(380, 300)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._setup_ui()
        self._load_into_ui()
        self._dragging = False
        self._offset = QPoint()

    def _load(self) -> dict:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._cfg, f, ensure_ascii=False, indent=2)

    # ── UI ────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 16)
        layout.setSpacing(10)

        # 标题栏
        title_bar = QHBoxLayout()
        title = QLabel("⚙ 设置")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {TEXT}; background: transparent; border: none;")
        title_bar.addWidget(title)
        title_bar.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; font-size: 15px; color: {MUTED}; }}
            QPushButton:hover {{ color: #C04040; }}
        """)
        close_btn.clicked.connect(self.close)
        title_bar.addWidget(close_btn)
        layout.addLayout(title_bar)

        # ── API Key
        layout.addWidget(self._section_label("豆包 API Key"))
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("ark-...")
        self._input_style(self._api_key)
        layout.addWidget(self._api_key)

        hint = QLabel("在 <a href='https://console.volcengine.com/ark'>火山引擎 Ark 平台</a> 获取")
        hint.setOpenExternalLinks(True)
        hint.setStyleSheet(f"font-size: 11px; color: {MUTED}; background: transparent; border: none;")
        layout.addWidget(hint)

        # ── Proactive 间隔
        layout.addWidget(self._section_label("主动说话频率"))
        self._proactive_interval = QComboBox()
        self._proactive_interval.addItem("每 15 分钟", 15)
        self._proactive_interval.addItem("每 20 分钟", 20)
        self._proactive_interval.addItem("每 30 分钟", 30)
        self._proactive_interval.addItem("每 60 分钟", 60)
        self._combo_style(self._proactive_interval)
        layout.addWidget(self._proactive_interval)

        # ── 开关项
        self._auto_start = QCheckBox("开机自动启动")
        self._check_style(self._auto_start)
        layout.addWidget(self._auto_start)

        self._music_glow = QCheckBox("音乐光环特效")
        self._check_style(self._music_glow)
        layout.addWidget(self._music_glow)

        layout.addStretch()

        # ── 保存按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("保存")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: #fff; border: none;
                border-radius: 8px; padding: 8px 32px;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #B89035; }}
        """)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _load_into_ui(self):
        self._api_key.setText(self._cfg.get("ark_api_key", ""))
        self._auto_start.setChecked(self._cfg.get("auto_start", False))
        self._music_glow.setChecked(self._cfg.get("music_glow", True))

        interval = self._cfg.get("proactive_interval", 20)
        for i in range(self._proactive_interval.count()):
            if self._proactive_interval.itemData(i) == interval:
                self._proactive_interval.setCurrentIndex(i)
                break

    def _on_save(self):
        self._cfg["ark_api_key"] = self._api_key.text().strip()
        self._cfg["auto_start"] = self._auto_start.isChecked()
        self._cfg["music_glow"] = self._music_glow.isChecked()
        self._cfg["proactive_interval"] = self._proactive_interval.currentData()
        self._save()

        if self._on_saved:
            self._on_saved(self._cfg)
        self.close()

    # ── 样式 helpers ──────────────────────────────────────────

    def _section_label(self, text: str) -> QLabel:
        lb = QLabel(text)
        lb.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {TEXT}; background: transparent; border: none; margin-top: 4px;")
        return lb

    def _input_style(self, w: QLineEdit):
        w.setStyleSheet(f"""
            QLineEdit {{
                padding: 7px 12px; border: 1.5px solid rgba(190,180,165,180);
                border-radius: 8px; font-size: 13px; background: rgba(255,255,255,130);
                color: {TEXT};
            }}
            QLineEdit:focus {{ border-color: {ACCENT}; background: rgba(255,255,255,200); }}
        """)

    def _combo_style(self, w: QComboBox):
        w.setStyleSheet(f"""
            QComboBox {{
                padding: 6px 12px; border: 1.5px solid rgba(190,180,165,180);
                border-radius: 8px; font-size: 13px; background: rgba(255,255,255,130);
                color: {TEXT};
            }}
            QComboBox:hover {{ border-color: {ACCENT}; }}
            QComboBox QAbstractItemView {{
                background: #FFF8F0; border: 1px solid #DDD0C0;
                selection-background-color: #E8D8C0; color: {TEXT};
            }}
        """)

    def _check_style(self, w: QCheckBox):
        w.setStyleSheet(f"""
            QCheckBox {{ font-size: 13px; color: {TEXT}; spacing: 8px; background: transparent; border: none; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; border: 1.5px solid #C0B0A0; background: rgba(255,255,255,130); }}
            QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
        """)

    # ── 背景 ──────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 16, 16)

        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 215))
        gradient.setColorAt(0.5, QColor(255, 255, 255, 175))
        gradient.setColorAt(1.0, QColor(248, 242, 232, 190))
        p.fillPath(path, QBrush(gradient))

        p.setPen(QPen(BORDER, 1))
        p.drawRoundedRect(0, 0, w - 1, h - 1, 16, 16)
        p.end()

    # ── 拖拽 ──────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._offset)

    def mouseReleaseEvent(self, event):
        self._dragging = False
