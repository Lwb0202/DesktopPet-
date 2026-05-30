"""宠物选择窗口 — 网格卡片展示，支持拖拽添加新宠物。"""

import os
import re
import shutil
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPixmap, QPainterPath, QFont,
    QMovie, QEnterEvent, QMouseEvent, QDragEnterEvent, QDropEvent,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QGridLayout, QFrame, QGraphicsDropShadowEffect, QDialog,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QSizePolicy,
)


# ═══════════════════════════════════════════════════════════════
#  宠物发现
# ═══════════════════════════════════════════════════════════════

def discover_pets(resources_dir: str) -> list[dict]:
    """发现所有可用宠物。支持旧 GIF 格式和新 PNG 序列格式。"""
    pets: list[dict] = [{"name": "默认猫咪", "type": "builtin", "path": None}]
    if not os.path.isdir(resources_dir):
        return pets
    for entry in sorted(os.scandir(resources_dir), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        # 新格式: assets/base/idle/*.png
        png_idle_dir = os.path.join(entry.path, "assets", "base", "idle")
        # 旧格式: idle.gif
        gif_idle = os.path.join(entry.path, "idle.gif")
        if os.path.isdir(png_idle_dir) and any(
            f.endswith(".png") for f in os.listdir(png_idle_dir)
        ):
            pets.append({"name": entry.name, "type": "png_seq", "path": entry.path})
        elif os.path.exists(gif_idle):
            pets.append({"name": entry.name, "type": "gif", "path": entry.path})
    return pets


def sanitize_name(name: str) -> str:
    """去除路径非法字符，限制长度。"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name).strip()
    return name[:40] if name else "未命名"


# ═══════════════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════════════

CARD_W, CARD_H = 148, 168
GRID_COLS = 3

CARD_STYLE = """
    PetCard {
        background: #fafaf8;
        border: 2px solid #e0ddd5;
        border-radius: 14px;
    }
    PetCard:hover {
        border: 2px solid #c8b896;
        background: #fffdf7;
    }
"""

ADD_CARD_STYLE = """
    AddCard {
        background: #f8f7f3;
        border: 2px dashed #d0cdc5;
        border-radius: 14px;
    }
    AddCard:hover {
        border: 2px dashed #b0a890;
        background: #fdfcf8;
    }
"""

DROP_ZONE_STYLE = """
    DropZone {
        background: #fafaf7;
        border: 2px dashed #d5d2c8;
        border-radius: 10px;
    }
    DropZone:hover {
        border: 2px dashed #b0a878;
        background: #fefdf9;
    }
"""

DIALOG_STYLE = """
    AddPetDialog {
        background: #f5f3ee;
        border: 1px solid #d0ccc0;
        border-radius: 16px;
    }
"""


# ═══════════════════════════════════════════════════════════════
#  PetCard
# ═══════════════════════════════════════════════════════════════

class PetCard(QFrame):
    clicked = pyqtSignal(dict)
    delete_requested = pyqtSignal(dict)

    def __init__(self, pet_info: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self._info = pet_info
        self._selected = False
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(CARD_STYLE)
        self._preview_pixmap: QPixmap | None = None
        self._setup_preview()

    @property
    def info(self) -> dict:
        return self._info

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self.setStyleSheet(CARD_STYLE + """
                PetCard { border: 3px solid #e0a050; background: #fffbf2; }
            """)
        else:
            self.setStyleSheet(CARD_STYLE)
        self.update()

    def _setup_preview(self) -> None:
        from animation import AnimationClip
        ptype = self._info["type"]
        clip = None

        if ptype == "png_seq":
            idle_dir = os.path.join(self._info["path"], "assets", "base", "idle")
            clip = AnimationClip.from_directory(idle_dir)
        elif ptype == "gif":
            idle_path = os.path.join(self._info["path"], "idle.gif")
            clip = AnimationClip.from_gif(idle_path)

        if clip and clip.frame and not clip.frame.isNull():
            self._preview_pixmap = clip.frame.scaled(
                CARD_W - 24, CARD_H - 52,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        preview_h = CARD_H - 40

        if self._preview_pixmap:
            pw, ph = self._preview_pixmap.width(), self._preview_pixmap.height()
            p.drawPixmap((CARD_W - pw) // 2, (preview_h - ph) // 2, self._preview_pixmap)
        else:
            self._draw_builtin_preview(p, CARD_W // 2, preview_h // 2)

        p.setPen(QColor(0x4A, 0x37, 0x28))
        font = QFont("Microsoft YaHei", 11)
        font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        name = self._info["name"]
        p.drawText(rect.adjusted(8, preview_h + 4, -8, 0),
                   Qt.AlignmentFlag.AlignHCenter, name)
        p.end()

    def _draw_builtin_preview(self, p: QPainter, cx: int, cy: int) -> None:
        s = 0.42
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 180, 100)))
        p.drawEllipse(int(cx - 28 * s), int(cy + 8 * s), int(56 * s), int(48 * s))
        p.setBrush(QBrush(QColor(255, 160, 80)))
        le = QPainterPath()
        le.moveTo(cx - 22 * s, cy - 18 * s)
        le.lineTo(cx - 8 * s, cy - 42 * s)
        le.lineTo(cx + 2 * s, cy - 20 * s)
        p.drawPath(le)
        re = QPainterPath()
        re.moveTo(cx + 2 * s, cy - 20 * s)
        re.lineTo(cx + 12 * s, cy - 42 * s)
        re.lineTo(cx + 22 * s, cy - 18 * s)
        p.drawPath(re)
        p.setBrush(QBrush(QColor(255, 210, 140)))
        p.drawEllipse(int(cx - 22 * s), int(cy - 30 * s), int(44 * s), int(40 * s))
        p.setBrush(QBrush(QColor(50, 30, 20)))
        p.drawEllipse(int(cx - 10 * s), int(cy - 14 * s), int(8 * s), int(9 * s))
        p.drawEllipse(int(cx + 6 * s), int(cy - 14 * s), int(8 * s), int(9 * s))
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(int(cx - 7 * s), int(cy - 17 * s), int(3 * s), int(3 * s))
        p.drawEllipse(int(cx + 9 * s), int(cy - 17 * s), int(3 * s), int(3 * s))
        p.setBrush(QBrush(QColor(255, 120, 120)))
        p.drawEllipse(int(cx - 2 * s), int(cy - 3 * s), int(5 * s), int(4 * s))
        pen = QPen(QColor(80, 50, 30), 1)
        p.setPen(pen)
        p.drawLine(int(cx), int(cy + 2 * s), int(cx - 6 * s), int(cy + 8 * s - 2))
        p.drawLine(int(cx), int(cy + 2 * s), int(cx + 6 * s), int(cy + 8 * s - 2))

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._info)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        if self._info["type"] == "builtin":
            return
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        delete_action = menu.addAction("删除宠物")
        delete_action.triggered.connect(
            lambda: self.delete_requested.emit(self._info)
        )
        menu.exec(event.globalPos())


# ═══════════════════════════════════════════════════════════════
#  AddCard — "+" 按钮卡片
# ═══════════════════════════════════════════════════════════════

class AddCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(ADD_CARD_STYLE)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # "+" 圆形图标
        cx, cy = CARD_W // 2, (CARD_H - 40) // 2
        r = 22
        p.setPen(QPen(QColor(0xC0, 0xB8, 0xA0), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        p.drawLine(cx - 10, cy, cx + 10, cy)
        p.drawLine(cx, cy - 10, cx, cy + 10)

        # 文字
        p.setPen(QColor(0x90, 0x88, 0x70))
        font = QFont("Microsoft YaHei", 11)
        p.setFont(font)
        p.drawText(self.rect().adjusted(8, CARD_H - 44, -8, 0),
                   Qt.AlignmentFlag.AlignHCenter, "添加宠物")
        p.end()

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════
#  DropZone — 拖拽 GIF 放置区
# ═══════════════════════════════════════════════════════════════

DROP_W, DROP_H = 130, 110


class DropZone(QFrame):
    file_changed = pyqtSignal(str)  # GIF 文件路径，"" 表示清除

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._label = label
        self._file_path = ""
        self._preview: QPixmap | None = None
        self.setAcceptDrops(True)
        self.setFixedSize(DROP_W, DROP_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(DROP_ZONE_STYLE)

    @property
    def file_path(self) -> str:
        return self._file_path

    def set_file(self, path: str) -> None:
        self._file_path = path
        self._preview = None
        if not path or not os.path.exists(path):
            self.update()
            return

        if os.path.isdir(path):
            # PNG 序列：取第一个 PNG 做预览
            for fname in sorted(os.listdir(path)):
                if fname.lower().endswith(".png"):
                    pm = QPixmap(os.path.join(path, fname))
                    if not pm.isNull():
                        self._preview = pm.scaled(
                            DROP_W - 20, DROP_H - 32,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    break
        elif path.lower().endswith(".gif"):
            movie = QMovie(path)
            movie.jumpToFrame(0)
            pm = movie.currentPixmap()
            movie.stop()
            if not pm.isNull():
                self._preview = pm.scaled(
                    DROP_W - 20, DROP_H - 32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        elif path.lower().endswith(".png"):
            pm = QPixmap(path)
            if not pm.isNull():
                self._preview = pm.scaled(
                    DROP_W - 20, DROP_H - 32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        if self._preview:
            pw, ph = self._preview.width(), self._preview.height()
            p.drawPixmap((DROP_W - pw) // 2, (DROP_H - 28 - ph) // 2, self._preview)
            fname = os.path.basename(self._file_path)
            if os.path.isdir(self._file_path):
                fname = f"📁 {fname}"
            p.setPen(QColor(0x60, 0x90, 0x50))
            font = QFont("Microsoft YaHei", 8)
            p.setFont(font)
            p.drawText(rect.adjusted(4, DROP_H - 28, -4, 0),
                       Qt.AlignmentFlag.AlignCenter, fname)
        else:
            p.setPen(QPen(QColor(0xB0, 0xA8, 0x90), 1, Qt.PenStyle.DashLine))
            inner = rect.adjusted(12, 12, -12, -32)
            p.drawRoundedRect(inner, 6, 6)
            p.setPen(QColor(0xA0, 0x98, 0x80))
            font = QFont("Microsoft YaHei", 9)
            p.setFont(font)
            label_text = self._label.replace("GIF", "").strip()
            p.drawText(inner, Qt.AlignmentFlag.AlignCenter, f"拖入\n{label_text}")
        p.end()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._has_gif(event.mimeData()):
            event.acceptProposedAction()
            self.setStyleSheet(DROP_ZONE_STYLE + """
                DropZone { border: 2px solid #c0a040; background: #fffef8; }
            """)

    def dragLeaveEvent(self, event) -> None:
        self.setStyleSheet(DROP_ZONE_STYLE)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setStyleSheet(DROP_ZONE_STYLE)
        path = self._first_gif(event.mimeData())
        if path:
            self.set_file(path)
            self.file_changed.emit(path)
            event.acceptProposedAction()

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton:
            # 弹出菜单选择"单个文件"或"PNG序列文件夹"
            from PyQt6.QtWidgets import QMenu
            menu = QMenu(self)
            file_action = menu.addAction("选择 GIF/PNG 文件")
            dir_action = menu.addAction("选择 PNG 序列文件夹")
            action = menu.exec(event.globalPos())
            if action == file_action:
                path, _ = QFileDialog.getOpenFileName(
                    self, f"选择 {self._label} 文件", "",
                    "图片文件 (*.gif *.png);;GIF (*.gif);;PNG (*.png)",
                )
                if path:
                    self.set_file(path)
                    self.file_changed.emit(path)
            elif action == dir_action:
                path = QFileDialog.getExistingDirectory(
                    self, f"选择 {self._label} PNG 序列文件夹")
                if path:
                    self.set_file(path)
                    self.file_changed.emit(path)
        super().mousePressEvent(event)

    @staticmethod
    def _has_gif(mime: QMimeData) -> bool:
        if mime.hasUrls():
            for url in mime.urls():
                f = url.toLocalFile()
                low = f.lower()
                if low.endswith(".gif") or low.endswith(".png"):
                    return True
                if os.path.isdir(f):
                    return True
        return False

    @staticmethod
    def _first_gif(mime: QMimeData) -> str:
        if mime.hasUrls():
            for url in mime.urls():
                path = url.toLocalFile()
                low = path.lower()
                if low.endswith(".gif") or low.endswith(".png"):
                    return path
                if os.path.isdir(path):
                    return path
        return ""


# ═══════════════════════════════════════════════════════════════
#  AddPetDialog
# ═══════════════════════════════════════════════════════════════

class AddPetDialog(QDialog):
    pet_created = pyqtSignal(str)  # 新宠物目录路径

    def __init__(self, resources_dir: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._resources_dir = resources_dir
        self.setWindowTitle("添加新宠物")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setObjectName("AddPetDialog")
        self.setStyleSheet(DIALOG_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._drop_zones: dict[str, DropZone] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # 标题
        title = QLabel("添加新宠物")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #4A3728; "
            "background: transparent; border: none;"
        )
        root.addWidget(title)

        # 名称输入
        name_row = QHBoxLayout()
        name_label = QLabel("名称：")
        name_label.setStyleSheet("background: transparent; font-size: 12px; color: #555;")
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("给宠物起个名字")
        self._name_input.setStyleSheet("""
            QLineEdit {
                padding: 6px 10px; border: 1px solid #d0ccc0;
                border-radius: 6px; background: #fff; font-size: 12px;
            }
            QLineEdit:focus { border-color: #c0a040; }
        """)
        name_row.addWidget(name_label)
        name_row.addWidget(self._name_input, 1)
        root.addLayout(name_row)

        # ── 图层拖拽区（分组）──
        layer_groups = [
            ("Base 层（身体动作）", [
                ("idle",       "待机 *"),
                ("sleep",      "睡觉"),
                ("dance",      "跳舞"),
                ("jump_rope",  "跳绳"),
                ("spin",       "转圈圈"),
            ]),
            ("Expression 层（表情）", [
                ("happy",  "开心"),
                ("sad",    "难过"),
                ("sleepy", "困倦"),
            ]),
            ("Overlay 层（特效）", [
                ("heart",  "爱心"),
                ("flower", "花瓣"),
                ("tear",   "泪滴"),
                ("ball",   "足球"),
                ("zzz",    "Zzz"),
                ("dots",   "..." ),
            ]),
        ]

        for group_name, states in layer_groups:
            group_label = QLabel(group_name)
            group_label.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #7A6A58; "
                "background: transparent; padding: 4px 0 2px 0;"
            )
            root.addWidget(group_label)

            zones_layout = QHBoxLayout()
            zones_layout.setSpacing(8)
            for state_key, label in states:
                zone = DropZone(label)
                zone.setFixedSize(72, 62)
                zone.file_changed.connect(
                    lambda p, k=state_key: self._on_file_changed(k, p))
                self._drop_zones[state_key] = zone

                col = QVBoxLayout()
                col.setSpacing(2)
                col.addWidget(zone, alignment=Qt.AlignmentFlag.AlignCenter)
                state_label = QLabel(label.replace(" *", ""))
                state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                state_label.setStyleSheet(
                    "font-size: 9px; color: #999; background: transparent;"
                )
                if "*" in label:
                    state_label.setStyleSheet(
                        "font-size: 9px; color: #c08040; font-weight: bold; "
                        "background: transparent;"
                    )
                col.addWidget(state_label)
                zones_layout.addLayout(col)
            zones_layout.addStretch()
            root.addLayout(zones_layout)

        # 提示
        hint = QLabel("支持拖入 GIF 文件或 PNG 序列文件夹\n"
                       "标记 * 的 idle 为必填，其他缺失时使用内置动画")
        hint.setStyleSheet(
            "font-size: 10px; color: #aaa; background: transparent; padding: 4px;"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(hint)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        cancel.setStyleSheet("""
            QPushButton {
                padding: 6px 20px; border: 1px solid #d0ccc0;
                border-radius: 6px; background: #f5f3ee; font-size: 12px;
            }
            QPushButton:hover { background: #e8e5dc; }
        """)
        btn_row.addWidget(cancel)
        confirm = QPushButton("确认添加")
        confirm.clicked.connect(self._on_confirm)
        confirm.setStyleSheet("""
            QPushButton {
                padding: 6px 20px; border: none; border-radius: 6px;
                background: #d4a853; color: #fff; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #c89830; }
        """)
        btn_row.addWidget(confirm)
        root.addLayout(btn_row)

        self.setFixedSize(640, self.sizeHint().height())

    def _on_file_changed(self, state_key: str, path: str) -> None:
        # 自动从文件名推断宠物名称
        if state_key == "idle" and path and not self._name_input.text():
            folder = os.path.basename(os.path.dirname(path))
            if folder and folder not in ("resources", "."):
                self._name_input.setText(folder)

    def _on_confirm(self) -> None:
        name = sanitize_name(self._name_input.text().strip())
        if not name:
            QMessageBox.warning(self, "提示", "请输入宠物名称")
            return

        idle_path = self._drop_zones["idle"].file_path
        if not idle_path:
            QMessageBox.warning(self, "提示", "请至少拖入待机 (idle) 素材")
            return

        dest_dir = os.path.join(self._resources_dir, name)
        if os.path.exists(dest_dir):
            QMessageBox.warning(self, "提示", f"宠物「{name}」已存在，请换个名字")
            return

        # 图层 → assets 子目录 映射
        _LAYER_DIRS = {
            # Base
            "idle":      "assets/base/idle",
            "sleep":     "assets/base/sleep",
            "dance":     "assets/base/dance",
            "jump_rope": "assets/base/jump_rope",
            "spin":      "assets/base/spin",
            # Expression
            "happy":  "assets/expression/happy",
            "sad":    "assets/expression/sad",
            "sleepy": "assets/expression/sleepy",
            # Overlay
            "heart":  "assets/overlay/heart",
            "flower": "assets/overlay/flower",
            "tear":   "assets/overlay/tear",
            "ball":   "assets/overlay/ball",
            "zzz":    "assets/overlay/zzz",
            "dots":   "assets/overlay/dots",
        }

        try:
            os.makedirs(dest_dir, exist_ok=True)
            for state_key, zone in self._drop_zones.items():
                src = zone.file_path
                if not src or not os.path.exists(src):
                    continue
                rel_dir = _LAYER_DIRS.get(state_key)
                if rel_dir is None:
                    continue
                target_dir = os.path.join(dest_dir, rel_dir)
                os.makedirs(target_dir, exist_ok=True)

                if os.path.isdir(src):
                    # PNG 序列目录 → 复制所有 PNG 文件
                    png_files = sorted(
                        f for f in os.listdir(src)
                        if f.lower().endswith(".png")
                    )
                    if png_files:
                        for fname in png_files:
                            shutil.copy2(
                                os.path.join(src, fname),
                                os.path.join(target_dir, fname),
                            )
                    else:
                        # 目录但无 PNG → 复制目录下所有文件
                        for fname in os.listdir(src):
                            fp = os.path.join(src, fname)
                            if os.path.isfile(fp):
                                shutil.copy2(fp, os.path.join(target_dir, fname))
                else:
                    # 单个文件（GIF/PNG）
                    ext = os.path.splitext(src)[1] or ".png"
                    shutil.copy2(src, os.path.join(target_dir, f"000{ext}"))
        except OSError as e:
            QMessageBox.warning(self, "错误", f"文件复制失败：{e}")
            return

        self.pet_created.emit(dest_dir)
        self.accept()


# ═══════════════════════════════════════════════════════════════
#  PetSelector
# ═══════════════════════════════════════════════════════════════

SELECTOR_STYLE = """
    PetSelector {
        background: #f5f3ee;
        border: 1px solid #d0ccc0;
        border-radius: 16px;
    }
    QScrollArea { background: transparent; border: none; }
    QScrollBar:vertical {
        background: transparent; width: 8px; margin: 4px 2px;
    }
    QScrollBar::handle:vertical {
        background: #c8c0b0; border-radius: 4px; min-height: 30px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class PetSelector(QWidget):
    pet_selected = pyqtSignal(dict)
    pet_deleted = pyqtSignal(str)  # 被删除宠物路径；内置猫删除时传 None

    def __init__(self, resources_dir: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._resources_dir = resources_dir
        self.setWindowTitle("选择宠物")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("PetSelector")
        self.setStyleSheet(SELECTOR_STYLE)
        self.setAcceptDrops(True)

        self._cards: list[PetCard] = []
        self._add_card: AddCard | None = None
        self._current_info: dict | None = None
        self._grid: QWidget | None = None
        self._scroll: QScrollArea | None = None

        self._build_ui()

    # ── UI 构建 ────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # 清除旧布局
        if self.layout():
            QWidget().setLayout(self.layout())

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)

        title = QLabel("选择宠物")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #4A3728; "
            "font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; "
            "background: transparent; border: none; padding: 4px;"
        )
        root.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid = QWidget()
        self._grid.setStyleSheet("background: transparent;")
        layout = QGridLayout(self._grid)
        layout.setSpacing(12)
        layout.setContentsMargins(8, 4, 8, 4)

        # 填充卡片
        self._cards.clear()
        pets = discover_pets(self._resources_dir)
        total = len(pets) + 1  # +1 for add card

        for i, info in enumerate(pets):
            card = PetCard(info)
            card.clicked.connect(self._on_card_clicked)
            card.delete_requested.connect(self._on_card_delete)
            self._cards.append(card)
            layout.addWidget(card, i // GRID_COLS, i % GRID_COLS,
                             Qt.AlignmentFlag.AlignCenter)

        # 添加 "+" 卡片
        add_index = len(pets)
        self._add_card = AddCard()
        self._add_card.clicked.connect(self._open_add_dialog)
        layout.addWidget(self._add_card, add_index // GRID_COLS,
                         add_index % GRID_COLS, Qt.AlignmentFlag.AlignCenter)

        # 补齐空位
        remainder = total % GRID_COLS
        if remainder:
            for j in range(GRID_COLS - remainder):
                spacer = QWidget()
                spacer.setFixedSize(CARD_W, CARD_H)
                spacer.setStyleSheet("background: transparent;")
                layout.addWidget(spacer, total // GRID_COLS, remainder + j)

        self._scroll.setWidget(self._grid)
        root.addWidget(self._scroll)

        # 窗口大小
        rows = max(1, (total + GRID_COLS - 1) // GRID_COLS)
        win_w = GRID_COLS * (CARD_W + 12) + 32
        win_h = rows * (CARD_H + 12) + 60
        self.setFixedSize(win_w, min(win_h, 620))

        # 阴影 — 改用更粗的边框替代，避免 QGraphicsEffect 导致黑背景
        self.setStyleSheet(SELECTOR_STYLE + """
            PetSelector { border: 1px solid #c8c0b0; }
        """)

    def _refresh(self) -> None:
        """重建整个网格（添加宠物后调用）。"""
        self._build_ui()

    # ── 卡片点击 ───────────────────────────────────────────────

    def _on_card_clicked(self, info: dict) -> None:
        for card in self._cards:
            card.set_selected(card.info == info)
        self._current_info = info
        self.pet_selected.emit(info)

    def _on_card_delete(self, info: dict) -> None:
        path = info["path"]
        name = info["name"]

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除宠物「{name}」吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 从磁盘删除
        if path and os.path.isdir(path):
            try:
                shutil.rmtree(path)
            except OSError as e:
                QMessageBox.warning(self, "错误", f"删除失败：{e}")
                return

        # 如果删的是当前选中的宠物，切回内置猫咪
        was_current = (self._current_info is not None
                       and self._current_info["path"] == path)

        self.pet_deleted.emit(path or "")

        self._refresh()

        if was_current:
            builtin_info = {"name": "默认猫咪", "type": "builtin", "path": None}
            for card in self._cards:
                card.set_selected(card.info == builtin_info)
            self._current_info = builtin_info
            self.pet_selected.emit(builtin_info)

    def _open_add_dialog(self) -> None:
        dlg = AddPetDialog(self._resources_dir, self)
        dlg.pet_created.connect(self._on_pet_created)
        dlg.exec()

    def _on_pet_created(self, dest_dir: str) -> None:
        self._refresh()
        # 新宠物自动选中
        name = os.path.basename(dest_dir)
        for card in self._cards:
            if card.info["path"] == dest_dir:
                self._on_card_clicked(card.info)
                return
        # 内置猫的路径是 None，如果匹配不到就用第一个 GIF 宠物
        for card in self._cards:
            if card.info["type"] == "gif" and card.info["path"] == dest_dir:
                self._on_card_clicked(card.info)
                return

    # ── 窗口拖拽接收（文件夹直接导入） ─────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                self._import_folder(path)
                event.acceptProposedAction()
                return
            elif path.lower().endswith(".gif"):
                # 单个 GIF → 打开对话框并预填
                dlg = AddPetDialog(self._resources_dir, self)
                dlg.pet_created.connect(self._on_pet_created)
                # 尝试自动分配
                basename = os.path.basename(path).lower()
                for key in ("idle", "sleep", "happy"):
                    if key in basename:
                        dlg._drop_zones[key].set_file(path)
                        dlg._drop_zones[key].file_changed.emit(path)
                        break
                else:
                    dlg._drop_zones["idle"].set_file(path)
                    dlg._drop_zones["idle"].file_changed.emit(path)
                # 用文件夹名作为名称
                folder = os.path.basename(os.path.dirname(path))
                if folder and folder not in ("resources", "."):
                    dlg._name_input.setText(folder)
                dlg.exec()
                event.acceptProposedAction()
                return

    def _import_folder(self, folder: str) -> None:
        """直接从文件夹导入宠物（自动识别文件名）。"""
        name = sanitize_name(os.path.basename(folder))
        dest = os.path.join(self._resources_dir, name)

        # 检查是否有 at least idle.gif
        found = False
        for fname in os.listdir(folder):
            low = fname.lower()
            if "idle" in low and low.endswith(".gif"):
                found = True
                break
        if not found:
            QMessageBox.warning(self, "提示",
                                f"文件夹「{name}」中未找到 idle 相关的 GIF 文件")
            return

        if os.path.exists(dest):
            QMessageBox.warning(self, "提示", f"宠物「{name}」已存在")
            return

        # 复制整个文件夹
        try:
            shutil.copytree(folder, dest)
        except OSError as e:
            QMessageBox.warning(self, "错误", f"复制失败：{e}")
            return

        # 标准化文件名
        state_map = {"idle": "idle", "sleep": "sleep", "happy": "happy"}
        for fname in os.listdir(dest):
            low = fname.lower()
            if not low.endswith(".gif"):
                continue
            for keyword, state_name in state_map.items():
                if keyword in low:
                    src = os.path.join(dest, fname)
                    dst = os.path.join(dest, f"{state_name}.gif")
                    if src != dst and not os.path.exists(dst):
                        os.rename(src, dst)
                    elif src != dst:
                        os.remove(src)
                    break

        self._refresh()
        # 自动选中新宠物
        for card in self._cards:
            if card.info["path"] == dest:
                self._on_card_clicked(card.info)
                return

    # ── 公开方法 ───────────────────────────────────────────────

    def set_current(self, path: str | None) -> None:
        for card in self._cards:
            card.set_selected(card.info["path"] == path)

    def show_at(self, global_pos) -> None:
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() - self.height() - 20
        screen = self.screen()
        if screen:
            geo = screen.availableGeometry()
            x = max(geo.left(), min(geo.right() - self.width(), x))
            y = max(geo.top(), min(geo.bottom() - self.height(), y))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
