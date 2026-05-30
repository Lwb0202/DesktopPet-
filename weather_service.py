"""天气服务 — IP 定位 + wttr.in 免费天气查询。"""

import json
import random
import logging
import urllib.request
import urllib.parse

_log = logging.getLogger("weather")


def _http_get(url: str, timeout: int = 5) -> dict | str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DesktopPet/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode()
            # 尝试解析 JSON
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
    except Exception as e:
        _log.debug(f"HTTP 请求失败: {e}")
        return None


def get_location() -> str:
    """通过 IP 获取城市名。"""
    try:
        result = _http_get("http://ip-api.com/json?fields=city")
        if isinstance(result, dict) and result.get("city"):
            return result["city"]
    except Exception:
        pass
    return "北京"


def get_weather(city: str | None = None) -> str:
    """获取天气摘要。

    Returns:
        例如 "☀️ 晴 26°C 湿度45% 风力2级"
    """
    if not city:
        city = get_location()

    try:
        # wttr.in 免费天气 API
        encoded = urllib.parse.quote(city)
        result = _http_get(
            f"https://wttr.in/{encoded}?format=j1",
            timeout=8,
        )
        if not isinstance(result, dict):
            return ""

        current = result.get("current_condition", [{}])[0]
        desc = current.get("weatherDesc", [{}])[0].get("value", "未知")
        temp = current.get("temp_C", "?")
        humidity = current.get("humidity", "?")
        wind = current.get("windspeedKmph", "?")

        # 天气图标映射
        icon_map = {
            "sunny": "☀️", "clear": "🌙", "partly cloudy": "⛅",
            "cloudy": "☁️", "overcast": "☁️", "mist": "🌫️", "fog": "🌫️",
            "rain": "🌧️", "light rain": "🌦️", "moderate rain": "🌧️",
            "heavy rain": "⛈️", "thunder": "⛈️", "snow": "❄️",
            "light snow": "🌨️", "drizzle": "🌦️",
        }
        desc_lower = desc.lower()
        icon = "🌈"
        for k, v in icon_map.items():
            if k in desc_lower:
                icon = v
                break

        return f"{icon} {city} {desc} {temp}°C 湿度{humidity}% 风力{wind}km/h"
    except Exception as e:
        _log.debug(f"天气查询失败: {e}")
        return ""


def get_weather_short(city: str | None = None) -> str:
    """获取简短天气（用于气泡）。"""
    if not city:
        city = get_location()
    try:
        encoded = urllib.parse.quote(city)
        result = _http_get(
            f"https://wttr.in/{encoded}?format=%c+%t+%h+%w",
            timeout=5,
        )
        if isinstance(result, str) and result.strip():
            return f"{city} {result.strip()}"
    except Exception:
        pass
    return ""


# ── 天气 → 心情映射 ──

WEATHER_BUBBLES = {
    "sunny": [
        "☀️ 阳光真好，想出去玩！",
        "今天天气超好，开心~",
        "晒太阳好舒服呀！",
    ],
    "clear": [
        "✨ 夜空很清澈呢",
        "星星好亮，适合许愿~",
    ],
    "rain": [
        "🌧️ 下雨了... 待在家里陪我吧",
        "下雨天最适合发呆",
        "雨声好好听，想睡觉...",
    ],
    "cloudy": [
        "☁️ 今天阴阴的",
        "云好多，太阳躲起来了",
    ],
    "thunder": [
        "⛈️ 打雷了！有点害怕...",
        "雷雨天躲在家里最安全！",
    ],
    "snow": [
        "❄️ 下雪了！好漂亮！",
        "雪白白的，好像棉花糖~",
    ],
    "mist": [
        "🌫️ 雾蒙蒙的，像在梦里",
        "外面啥也看不清...",
    ],
    "hot": [
        "🥵 好热啊... 要融化了",
        "夏天太热了，开空调吧！",
    ],
    "cold": [
        "🥶 好冷... 想窝在被窝里",
        "冷死了！快穿多点！",
    ],
    "default": [
        "今天天气还行~",
        "窗外天气好像还可以",
    ],
}


def get_weather_mood(weather_desc: str) -> tuple[str, str]:
    """根据天气描述返回 (气泡消息, 情绪)。

    Returns:
        (bubble_text, emotion_name) — emotion_name: happy/sad/sleepy/neutral
    """
    desc_lower = weather_desc.lower()

    # 温度判断
    if "°c" in weather_desc or "temp" in str(weather_desc):
        pass  # handled below

    mapping = []
    for keyword, bubbles in WEATHER_BUBBLES.items():
        if keyword in desc_lower:
            mapping.append((keyword, bubbles))
            break

    if mapping:
        key, bubbles = mapping[0]
        msg = random.choice(bubbles)

        if "sunny" in desc_lower:
            mood = "happy"
        elif "rain" in desc_lower:
            mood = "sad"
        elif "snow" in desc_lower:
            mood = "happy"
        elif "thunder" in desc_lower:
            mood = "sad"
        elif "clear" in desc_lower:
            mood = "sleepy"
        elif "mist" in desc_lower:
            mood = "sleepy"
        else:
            mood = "neutral"

        return msg, mood
    else:
        return random.choice(WEATHER_BUBBLES["default"]), "neutral"
