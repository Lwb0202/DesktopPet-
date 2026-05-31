# 桌面宠物 (Desktop Pet)

基于 PyQt6 的 Windows 桌面宠物应用，支持分层动画、AI 对话、主动说话、桌面依附、长期记忆、情绪系统、音乐可视化、天气感知、全屏检测、配置面板等功能。

---

## 目录结构

```
DesktopPet/
├── main.py                # 应用入口，子系统编排 + 系统托盘
├── pet_window.py          # 宠物窗口，11 状态机 + 分层动画 + 拖尾 + 地面阴影
├── pet_selector.py        # 宠物选择器，支持 GIF/PNG 序列
├── window_monitor.py      # Windows 前台窗口监听（纯 ctypes）
├── event_system.py        # 主动事件引擎（工作提醒/深夜/空闲）
├── desktop_attachment.py  # 桌面窗口依附（坐窗边、跟随、滑落）
├── desktop_marks.py       # 桌面痕迹（脚印/Zzz/涂鸦）
├── project_companion.py   # 项目陪伴引擎（全软件追踪+卸载检测）
├── music_visualizer.py    # 音乐歌词可视化（SMTC + 网易云歌词）
├── weather_service.py     # 天气查询（设备 GPS 优先 + wttr.in）
├── proactive_chat.py      # 宠物主动说话（AI 生成 + 知乎热点）
├── settings_dialog.py     # 图形化配置面板（液态玻璃风格）
├── data_paths.py          # 统一数据目录管理（%APPDATA%）
├── tick_manager.py        # 统一 Tick 分发器（单例）
├── config.example.json    # 配置模板（空 Key，供分发用）
├── requirements.txt       # Python 依赖
├── memory.json            # 长期记忆（自动生成）
├── project_data.json      # 项目陪伴数据（自动生成）
├── pet.log                # 运行日志（自动生成，5MB 轮转）
├── resources/             # 宠物素材
├── animation/
│   ├── clip.py            # AnimationClip — PNG 序列/GIF 加载
│   ├── layer.py           # AnimationLayer — 独立的动画图层
│   ├── controller.py      # AnimationController — 三层合成 + 地面阴影
│   └── builtin.py         # 内置猫程序化动画（15 个 clip，懒加载）
├── ai/
│   ├── __init__.py
│   ├── doubao_api.py      # 豆包 AI 对话客户端（滑动窗口防溢出）
│   ├── chat_dialog.py     # 液态玻璃聊天窗口
│   ├── memory_manager.py  # 长期记忆管理
│   └── emotion_state.py   # 情绪状态管理
```

---

## 环境要求

- Python 3.10+
- Windows 系统

### 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 依赖

| 包      | 版本    | 用途                   |
| ------- | ------- | ---------------------- |
| PyQt6   | >=6.5.0 | GUI 框架               |
| openai  | >=1.0   | 豆包 API 调用          |
| requests | >=2.31 | 热点/歌词/百度 API 请求 |
| winsdk  | —       | Windows 媒体控件（歌名）|

---

## 启动

```bash
.venv\Scripts\python.exe main.py
```

---

## 功能详解

### 1. 桌面宠物窗口 (`pet_window.py`)

#### 状态机

宠物拥有 **11 种状态**，通过概率自动切换（情绪系统和深夜模式会动态修正权重）：

| 状态                | 描述                | 持续时间 |
| ------------------- | ------------------- | -------- |
| `IDLE` (待机)       | 轻微弹跳动画，眨眼  | 10-25s   |
| `WANDER` (闲逛)     | 随机目标点平滑移动  | 4-10s    |
| `SLEEP` (睡觉)      | 闭眼、轻微浮动、Zzz | 10-25s   |
| `HAPPY` (开心)      | 大幅弹跳、爱心特效  | 3-6s     |
| `STARE` (发呆)      | 半睁眼、小瞳孔      | 5-12s    |
| `DANCE` (跳舞)      | 扭动身体            | 5-10s    |
| `CELEBRATE` (撒花)  | 撒花庆祝            | 4-8s     |
| `SPIN` (转圈圈)     | 原地旋转            | 3-6s     |
| `JUMP_ROPE` (跳绳)  | 上下跳动            | 4-7s     |
| `HEAD_BALL` (顶球)  | 顶足球              | 4-8s     |
| `CRY` (大哭)        | 伤心哭泣            | 5-10s    |

**基础状态切换规则（从 IDLE 出发）：**

```
IDLE → WANDER (15%) / SLEEP (8%) / STARE (8%) / HAPPY (8%) /
        DANCE (10%) / CELEBRATE (8%) / SPIN (8%) /
        JUMP_ROPE (6%) / HEAD_BALL (6%) / CRY (5%) / IDLE (18%)
其他状态 → IDLE (100%)
```

闲逛中不会被状态计时器打断，到达目标后自动切回 IDLE。

状态权重受到以下系统动态修正：

- **深夜模式**：SLEEP 权重 x3，WANDER/HAPPY 权重 x0.4
- **情绪系统**：见下文「情绪状态管理」

#### 鼠标交互

| 操作     | 行为                                                                                      |
| -------- | ----------------------------------------------------------------------------------------- |
| **拖动** | 按住左键拖动，带拖尾残影；拖到屏幕边缘松手 → 自动扒边探头                         |
| **单击** | 显示气泡文字（按情绪选取），通知情绪系统记录点击；若处于 SLEEP/STARE/WANDER 则唤醒为 IDLE |
| **双击** | 打开 AI 聊天对话框（300ms 间隔内两次点击）                                                |
| **右键** | 弹出菜单：更换宠物 / 退出                                                                 |

#### 视觉效果

- **地面阴影**：帧合成底层绘制半透明椭圆阴影，宠物不再"浮空"
- **拖尾残影**：拖动时身后拖出 4 个渐隐残影窗口（透明度 22% → 4%），松手消失
- **胡须 + 前脚**：左右各 3 根弯曲胡须，身体底部两只小前脚，坐姿更完整
- **耳朵动画**：左右耳尖独立摆动（不同频率/相位），随身体弹跳自然晃动
- **眨眼优化**：每周期仅眨眼 1 次（闭眼 2 帧 / 133ms），不再频繁

#### 内置后备动画

当没有加载外部 PNG 资源时（默认猫咪），使用 `QPainter` 程序化绘制猫咪。所有动画帧通过懒加载工厂模式按需生成，启动仅加载 idle 帧，其他首次使用时生成。当前帧数：12 帧 @ 15fps（idle）、10 帧 @ 10fps（sleep）等。

#### 公开 API（供事件/情绪系统调用）

| 方法                      | 说明                              |
| ------------------------- | --------------------------------- |
| `show_bubble(text)`       | 显示气泡文字                      |
| `set_sleepy(enabled)`     | 启用/禁用深夜模式（影响状态权重） |
| `start_wander()`          | 强制触发闲逛状态                  |
| `set_emotion_manager(em)` | 注入情绪管理器                    |
| `sit_still()`             | 强制静坐（供依附系统调用）        |
| `freeze()` / `unfreeze()` | 冻结/解冻（启动时 5 分钟静止）   |

---

### 2. 宠物选择器 (`pet_selector.py`)

#### 网格卡片浏览

- 3 列网格布局展示所有可用宠物
- 每个卡片显示 GIF 首帧预览图 + 名称
- 点击卡片选中（橙色高亮边框），切换桌面宠物
- 右键卡片 → "删除宠物"（需确认，内置猫咪不可删除）

#### 添加新宠物（三种方式）

**方式一：点 "+" 卡片**

1. 弹出 `AddPetDialog` 对话框
2. 输入宠物名称
3. 分别拖入/选择 `idle.gif`（必填）、`sleep.gif`（可选）、`happy.gif`（可选）
4. 点击确认 → 自动复制到 `resources/<名称>/` 目录

**方式二：拖拽单个 GIF 到选择器窗口**

- 自动识别文件名关键词（idle/sleep/happy）分配到对应状态
- 自动用文件夹名预填宠物名称

**方式三：拖拽文件夹到选择器窗口**

- 自动检测文件夹中是否有 idle 相关 GIF
- 复制整个文件夹到 resources
- 自动标准化文件名（含 idle/sleep/happy 的 → `idle.gif` 等）

#### 配置持久化

选中的宠物记录在 `config.json` 中，下次启动自动恢复。

---

### 3. 窗口监听 (`window_monitor.py`)

纯 ctypes 实现，无第三方依赖。通过 TickManager 轮询前台窗口。

| 项目       | 说明                                                    |
| ---------- | ------------------------------------------------------- |
| 轮询间隔   | 500ms                                                   |
| 信号       | `window_changed(old_info, new_info)` — 仅窗口切换时触发 |
| WindowInfo | `hwnd`, `title`, `process_name`                         |

窗口切换同时驱动：

- **长期记忆**：记录应用使用次数
- **熬夜检测**：23:00-06:00 间的操作记录为熬夜
- **事件系统**：重置空闲计时器
- **项目追踪**：记录所有软件使用时长

---

### 4. AI 对话 (`ai/`)

#### 豆包 API 客户端 (`doubao_api.py`)

封装豆包（Ark）开放平台 API，使用 OpenAI 兼容协议。

**API Key 读取优先级：**

1. 构造函数传参：`DoubaoChat(api_key="...")`
2. 环境变量：`ARK_API_KEY`
3. 配置文件：`config.json` → `ark_api_key`

```python
from ai import DoubaoChat

bot = DoubaoChat()
reply = bot.chat("你好")
bot.clear_context()
```

**技术细节：**

- 模型：`doubao-seed-2-0-pro-260215`
- Base URL：`https://ark.cn-beijing.volces.com/api/v3`
- 滑动窗口：最多保留最近 40 条消息（20 轮对话），防止 token 超限
- 首次无 Key → 自动弹出设置对话框引导输入

#### 液态玻璃聊天窗口 (`chat_dialog.py`)

双击宠物弹出，始终置顶。

| 特性     | 说明                                                          |
| -------- | ------------------------------------------------------------- |
| 视觉效果 | 半透明白色渐变、圆角、内外发光边框、顶部高光 — 模拟毛玻璃质感 |
| 初始位置 | 屏幕可用区域左下角，距边缘 30px                               |
| 拖动     | 拖拽标题栏任意移动                                            |
| 关闭     | 右上角 ✕ 按钮，`WA_DeleteOnClose` 自动释放                   |
| 对话角色 | 自动读取 `config.json` 中当前宠物名称                         |
| 发送     | Enter 键或点击"发送"按钮                                      |
| 防重复   | 等待回复期间输入框和按钮禁用                                  |
| 错误处理 | API 异常时显示友好中文提示                                    |

**AI 对话上下文注入（自动）：**

1. **长期记忆上下文** — 用户常用软件、关注话题、活跃时间
2. **情绪上下文** — 宠物当前情绪状态
3. **项目上下文** — 活跃/搁置项目摘要
4. **用户消息** — 原始输入

---

### 5. 长期记忆 (`ai/memory_manager.py`)

纯数据层模块，JSON 本地存储。

#### 存储结构 (`memory.json`)

```json
{
  "app_usage": { "VS Code": { "count": 150, "last_used": "2026-05-25T14:30:00" } },
  "daily_active": { "2026-05-25": { "start": "09:00" } },
  "chat_keywords": ["Python", "Bug", "编程"],
  "late_nights": [ { "date": "2026-05-25", "end": "02:30", "apps": ["VS Code"] } ]
}
```

#### API

```python
from ai import MemoryManager
m = MemoryManager()
m.record_app("VS Code")
m.record_chat("我想学Python")
m.top_apps()        # → [("VS Code", 150), ...]
m.get_context_for_ai()  # → 可供 AI 注入的记忆文本
```

---

### 6. 主动事件系统 (`event_system.py`)

基于 TickManager 的条件驱动引擎，每 30s 检查和三类事件：

| 事件 | 触发条件 | 行为 |
|------|---------|------|
| 连续工作提醒 | 累计活跃 ≥90 分钟 | 气泡提醒休息，60 分钟冷却 |
| 深夜模式 | 23:00-06:00 | SLEEP 权重 x3 + 晚安气泡 |
| 空闲闲逛 | ≥30 分钟无键鼠操作 | 宠物强制 WANDER |

---

### 7. 情绪状态管理 (`ai/emotion_state.py`)

30 分钟持续情绪，影响气泡文本、动画频率和 AI 对话。

|                 | NEUTRAL           | HAPPY                        | SAD                          |
| --------------- | ----------------- | ---------------------------- | ---------------------------- |
| **触发条件**    | 默认 / 30min 过期 | 10s 内点击 ≥5 次             | 聊天含负面关键词             |
| **HAPPY 权重**  | x1.0              | x2.5                         | x0.1                         |
| **SLEEP 权重**  | x1.0              | x0.3                         | x2.0                         |
| **AI 上下文**   | 无                | "宠物现在心情很好"           | "宠物情绪有些低落"           |

---

### 8. 桌面依附系统 (`desktop_attachment.py`)

宠物与前台窗口物理互动——自动坐窗口边缘、跟随移动、快速甩动时滑落。

**三种状态：** `GROUNDED` → 检测吸附 → `ATTACHED`（lerp 跟随）→ 抖动/切换窗口 → `FALLING`（加速下落）→ 落地 = `GROUNDED`

**关键参数：** lerp 0.25、下落加速 0.8 px/tick²、最大 16 px/tick、落地 6 秒冷却防震荡。下落过程中不检测吸附窗口，直接落到底部，避免"下落→吸附→再下落"的抽搐循环。

---

### 9. 桌面痕迹系统 (`desktop_marks.py`)

用户空闲 >30 分钟时在桌面留下 paw / Zzz / star / heart 等痕迹，独立透明窗口，淡入 2s → 存活 10 分钟 → 淡出 3s，最多 5 个。用户有任何操作（切换窗口/移动鼠标/按键）时痕迹立即自动清除。

---

### 10. 项目陪伴引擎 (`project_companion.py`)

动态追踪所有软件使用，自动识别长期项目和搁置项目，检测已卸载软件。排除 50+ 通讯/浏览器/娱乐进程。AI 上下文注入活跃和搁置项目摘要。

---

### 11. 分层动画系统 (`animation/`)

Base / Expression / Overlay 三层 QPainter 合成。内置猫咪通过懒加载工厂按需生成帧（启动时仅生成 idle）。

#### 内置帧参数（当前）

| Base 层 | Expression 层 | Overlay 层 |
|---------|--------------|------------|
| idle (12 frames, 15fps) | happy (12 frames, 15fps) | heart (10 frames, 12fps) |
| sleep (10 frames, 10fps) | sad (10 frames, 10fps) | zzz (8 frames, 10fps) |
| dance (12 frames, 12fps) | sleepy (10 frames, 10fps) | dots (6 frames, 8fps) |
| jump_rope (12 frames, 15fps) | | flower (10 frames, 12fps) |
| spin (10 frames, 10fps) | | tear (8 frames, 10fps) |
| | | ball (8 frames, 10fps) |

#### 状态 → 图层映射

| PetState | Base | Expression | Overlay |
|----------|------|------------|---------|
| IDLE / WANDER | idle | — | — |
| SLEEP | sleep | — | zzz |
| HAPPY | idle | happy | heart |
| STARE | idle | sleepy | dots |
| CELEBRATE | idle | happy | flower |
| DANCE | dance | — | — |
| JUMP_ROPE | jump_rope | — | — |
| HEAD_BALL | idle | — | ball |
| CRY | idle | sad | tear |
| SPIN | spin | — | — |

合成顺序：地面阴影 → Base → Expression → Overlays

---

### 12. 音乐歌词可视化 (`music_visualizer.py`)

**检测链路：** SMTC (winsdk) → 歌名 → 网易云 API 歌词 → LRC 时间轴匹配

**视觉效果：**

- 歌词沿弧线单行显示，3D 纵深：近大远小、近亮远暗
- 带时间轴时每句随播放进度自动切换；无时间轴时每 5 秒翻一行
- 暂停冻结，切歌自动刷新
- 拖拽进度条后自动检测跳变（差值 >3s），立即重同步  
- 音乐停止后 90s 位置停滞自动隐藏，关闭软件强制清除 SMTC 缓存
- 三圈渐变呼吸光环（托盘菜单可开关，持久化到 `config.json`）
- 每个字符随机 RGB 亮色

**支持的音乐软件：** 网易云、QQ 音乐、Spotify、酷狗、foobar2000 等

---

### 13. 宠物主动说话 (`proactive_chat.py`)

无需打开对话框，宠物定时主动冒出一句话。

- 每 **15 分钟 ± 2 分钟**（可在设置面板调整 15/20/30/60 分钟）
- 组装时间、陪伴天数、情绪、项目、记忆上下文
- 从知乎热榜获取今日热点头条（免费，缓存 30 分钟）
- 调用 AI 生成 1-2 句自然可爱的话（≤25 字）
- 以气泡展示，不打开对话框
- API 不可用时静默跳过
- 里程碑日（7/30/100/365 天）自动庆祝

---

### 14. 配置面板 (`settings_dialog.py`)

从托盘菜单 **"设置..."** 打开，液态玻璃风格 GUI：

- **豆包 API Key** — 密码遮罩输入，带获取链接
- **主动说话频率** — 下拉选择 15/20/30/60 分钟
- **开机自动启动** — 复选框
- **音乐光环特效** — 复选框
- **保存** — 写入 `config.json` 即时生效

---

### 15. 系统托盘 + 全屏检测

- 任务栏右下角猫头图标，双击显隐宠物
- 右键菜单：显隐 / 更换宠物 / 设置 / 开机自启 / 音乐光环 / 退出
- 首次运行弹窗询问是否开机自启（注册表方式，非 VBS）
- **全屏检测**：前台窗口覆盖整个屏幕时自动隐藏宠物 + 暂停动画，退出全屏恢复
- **用户活跃检测**：操作时宠物不移动，停止操作 60s 后恢复闲逛

---

### 16. 天气感知 (`weather_service.py`)

每 30 分钟后台线程查询天气（优先 Windows 设备 GPS 定位，回退 ip-api + wttr.in），气泡表达天气心情。

---

### 17. 统一 Tick 分发器 (`tick_manager.py`)

单例模式，合并高频定时器为单一 16ms tick。

| 注册名 | 间隔 | 用途 |
|--------|------|------|
| `anim` | 16ms | 动画更新 + 合成 + 拖尾 |
| `wander` | 33ms | 闲逛移动 |
| `bubble_follow` | 50ms | 气泡跟随宠物 |
| `attach` | 40ms | 桌面依附检测 |
| `music_viz` | 33ms | 歌词旋转更新 |
| `fullscreen` | 800ms | 全屏检测 |

特性：`pause_all()` / `resume_all()` 全局暂停恢复，回调超时告警，单回调异常不影响其他。

---

### 18. 日志系统

`logging` 替代全项目 `print()`。`RotatingFileHandler`（5MB × 2 备份）同时输出控制台。

格式：`HH:MM:SS [模块名] 消息`

---

## 性能优化

- **懒加载动画**：启动仅生成 idle 帧（12 帧），切换状态时再按需生成
- **Tick 合并**：5+ 个高频定时器合并为 1 个 TickManager 16ms tick
- **天气后台线程**：HTTP 请求 daemon 线程，不阻塞 UI
- **双缓冲合成**：`composite()` 缓存脏帧，避免重复绘制
- **DoubaoChat 滑动窗口**：最多 40 条消息，防止 token 超限
- **热点缓存**：知乎热榜 30 分钟缓存

---

## 模块依赖关系图

```
main.py
  ├── PetWindow ←── AnimationController (分层合成 + 阴影)
  ├── PetWindow ←── TickManager (统一 tick)
  ├── PetWindow ←── EmotionManager (情绪影响)
  ├── PetWindow ←── EventSystem (深夜/空闲/工作提醒)
  ├── PetWindow ←── DesktopAttachment (窗口吸附)
  ├── PetWindow ←── DeskMarkManager (桌面痕迹)
  ├── PetWindow ←── ProjectCompanion (项目陪伴)
  ├── PetWindow ←── ProactiveChat (主动说话)
  ├── ChatDialog ←── EmotionManager + MemoryManager + ProjectCompanion
  ├── ChatDialog ←── DoubaoChat (AI 核心)
  ├── SettingsDialog → config.json (配置面板)
  ├── MusicVisualizer ←── winsdk/SMTC + NeteaseAPI
  ├── WindowMonitor → MemoryManager + ProjectCompanion
  └── WeatherService (后台线程)
```

---

## 配置文件 (`config.json`)

```json
{
  "pet": "默认猫咪",
  "resources_path": null,
  "ark_api_key": "your-ark-key",
  "auto_start": true,
  "music_glow": true,
  "proactive_interval": 15,
  "first_launch": "2026-05-31"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `pet` | string | 当前宠物名称 |
| `resources_path` | string\|null | 宠物资源目录 |
| `ark_api_key` | string | 豆包 Ark API Key |
| `auto_start` | bool | 开机自启动 |
| `music_glow` | bool | 音乐光环开关 |
| `proactive_interval` | int | 主动说话间隔（分钟） |

---

## 数据存储

所有持久化数据统一放在 `%APPDATA%\DesktopPet\`（不随版本更新丢失）：

| 文件 | 说明 | 上限 |
|------|------|------|
| `config.json` | 配置（API Key、偏好等） | ~1KB |
| `memory.json` | 长期记忆（App 使用、熬夜记录） | 自动修剪旧数据 |
| `project_data.json` | 项目陪伴数据 | 自动清理已卸载/低频软件 |
| `pet.log` | 运行日志 | 5MB × 2 滚动覆盖 |

**数据修剪策略**：启动时自动裁旧数据 — 熬夜记录保留 90 天、活跃记录保留 180 天、App 白名单 Top 200、极少使用的软件（<3 分钟 + 90 天未开）自动清理。

**卸载**：托盘菜单「打开数据目录」→ 手动删除 `%APPDATA%\DesktopPet\`。

---

## 打包分发

```bash
# 精简打包（单文件 53MB，已排除未用 Qt 模块）
.venv\Scripts\pyinstaller DesktopPet.spec --distpath dist3 --workpath build3 --noconfirm
```

- 输出 `dist3\DesktopPet.exe`（53MB 单文件）
- 仅打包 `config.example.json`（空 Key 模板），**不含你的真实 Key**

---

## 如何获取 API Key

访问 [火山引擎 Ark 平台](https://console.volcengine.com/ark)，创建 API Key，填入设置面板或 `config.json` 的 `ark_api_key`。

> 参考文档：https://www.volcengine.com/docs/82379/1399008
