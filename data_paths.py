"""统一数据目录 — 所有持久化文件存放到 %APPDATA%\DesktopPet\。"""

import os
import shutil
import logging

_log = logging.getLogger("data")

# 数据目录（不随版本更新变化）
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "DesktopPet")

# 各持久化文件路径
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
MEMORY_PATH = os.path.join(DATA_DIR, "memory.json")
PROJECT_DATA_PATH = os.path.join(DATA_DIR, "project_data.json")
LOG_PATH = os.path.join(DATA_DIR, "pet.log")

# 应用目录中的静态文件
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_EXAMPLE_PATH = os.path.join(_APP_DIR, "config.example.json")
RESOURCES_DIR = os.path.join(_APP_DIR, "resources")


def init_data_dir():
    """创建数据目录，从旧位置迁移已有数据。"""
    os.makedirs(DATA_DIR, exist_ok=True)

    # 迁移：app 目录 → 数据目录
    migrations = {
        os.path.join(_APP_DIR, "config.json"): CONFIG_PATH,
        os.path.join(_APP_DIR, "memory.json"): MEMORY_PATH,
        os.path.join(_APP_DIR, "project_data.json"): PROJECT_DATA_PATH,
    }

    for old_path, new_path in migrations.items():
        if os.path.isfile(old_path) and not os.path.exists(new_path):
            shutil.move(old_path, new_path)
            _log.info(f"数据已迁移: {os.path.basename(old_path)} → {DATA_DIR}")

    # 首次运行：复制模板配置
    if not os.path.exists(CONFIG_PATH) and os.path.isfile(CONFIG_EXAMPLE_PATH):
        shutil.copy2(CONFIG_EXAMPLE_PATH, CONFIG_PATH)
        _log.info("[配置] 已从 config.example.json 生成初始配置")
