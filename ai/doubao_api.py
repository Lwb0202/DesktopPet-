import os
import json
import logging
from openai import OpenAI

_log = logging.getLogger("doubao")

CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "DesktopPet", "config.json"
)


class DoubaoChat:
    """豆包开放平台对话客户端，支持上下文记忆。"""

    def __init__(self, api_key=None, model="doubao-seed-2-0-pro-260215"):
        if api_key is None:
            api_key = os.getenv("ARK_API_KEY")
        if api_key is None:
            api_key = self._load_key_from_config()

        if not api_key:
            raise ValueError(
                "未找到 API Key，请通过以下任一方式提供：\n"
                "  1. 传参: DoubaoChat(api_key='your-key')\n"
                "  2. 环境变量: export ARK_API_KEY='your-key'\n"
                "  3. 配置文件: 在 config.json 中设置 ark_api_key 字段"
            )

        self.client = OpenAI(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=api_key,
            timeout=30.0,
        )
        self.model = model
        self.messages = []
        _log.info("DoubaoChat 初始化完成, model=%s", model)

    def _load_key_from_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("ark_api_key")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    @classmethod
    def is_configured(cls) -> bool:
        """检查是否有可用的 API Key。"""
        key = os.getenv("ARK_API_KEY")
        if key:
            return True
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return bool(cfg.get("ark_api_key"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False

    @staticmethod
    def save_key_to_config(api_key: str) -> None:
        """将 API Key 保存到 config.json。"""
        cfg = {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        cfg["ark_api_key"] = api_key
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    MAX_HISTORY = 40  # 保留最近 20 轮对话

    def chat(self, message, timeout=25.0):
        """发送消息并返回 AI 回复文本，自动维护对话上下文。"""
        self.messages.append({"role": "user", "content": message})

        _log.info("发送 API 请求, 消息长度=%d, 历史=%d条", len(message), len(self.messages))
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            timeout=timeout,
        )

        reply = response.choices[0].message.content
        self.messages.append({"role": "assistant", "content": reply})
        _log.info("API 回复, 长度=%d", len(reply) if reply else 0)

        # 防止上下文无限增长：保留最近 N 条消息
        if len(self.messages) > self.MAX_HISTORY:
            self.messages = self.messages[-self.MAX_HISTORY:]

        return reply

    def clear_context(self):
        """清空对话历史。"""
        self.messages.clear()

    def get_history(self):
        """返回当前对话历史（浅拷贝）。"""
        return list(self.messages)
