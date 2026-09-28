from PySide6.QtGui import QColor

KEY_LABELS = ["z", "x", "c", "v", "b", "n", "m", ","]
DEFAULT_NOTE_KEYS = ["z", "x", "c", "v", "b", "n", "m", "comma"]
KEY_INDEX = {k: i for i, k in enumerate("zxcvbnm,")}

# 音符块配色（简洁深色）
# 6 种状态：本音 / 降调 / 半音 / 升调 / 半+降 / 半+升
STATE_STYLE = [
    dict(fill=QColor(0xF1, 0xF5, 0xF9), text=QColor(0x0F, 0x17, 0x2A)),  # 0 本音：灰白
    dict(fill=QColor(0x10, 0xB9, 0x81), text=QColor(0xFF, 0xFF, 0xFF)),  # 1 降调：绿
    dict(fill=QColor(0x8B, 0x5C, 0xF6), text=QColor(0xFF, 0xFF, 0xFF)),  # 2 半音：紫
    dict(fill=QColor(0x3B, 0x82, 0xF6), text=QColor(0xFF, 0xFF, 0xFF)),  # 3 升调：蓝
    dict(fill=QColor(0xF5, 0x9E, 0x0B), text=QColor(0x0F, 0x17, 0x2A)),  # 4 半+降：橙黄
    dict(fill=QColor(0xEF, 0x44, 0x44), text=QColor(0xFF, 0xFF, 0xFF)),  # 5 半+升：红
]

STRIP_COLORS = [QColor(0xF1, 0xF5, 0xF9), QColor(0x10, 0xB9, 0x81),
                QColor(0x8B, 0x5C, 0xF6), QColor(0x3B, 0x82, 0xF6),
                QColor(0xF5, 0x9E, 0x0B), QColor(0xEF, 0x44, 0x44)]

STATE_TOKEN_PREFIX = {0: "", 1: "b", 2: "#", 3: "^", 4: "#b", 5: "#^"}
PREFIX_CHARS = "b#^"
MOD_ROLES = ["降调", "半音", "升调"]
STATE_NAMES = ["本音", "降调", "半音", "升调", "半音+降调", "半音+升调"]
STATE_SHORT = ["本音", "降调", "半音", "升调", "半+降", "半+升"]
STATE_MODS = [[], ["降调"], ["半音"], ["升调"], ["半音", "降调"], ["半音", "升调"]]
CHIP_LAYOUT = [1, 0, 3, 4, 2, 5]

# Apple 风格浅色主题（用于游戏内悬浮面板，与主窗口统一）
THEME = {
    # 背景
    "bg_deep": QColor(0xF2, 0xF2, 0xF7),           # 浅灰底
    "bg_panel": QColor(0xFF, 0xFF, 0xFF, 0xE8),    # 面板背景（带透明度）
    "bg_card": QColor(0xFF, 0xFF, 0xFF),           # 卡片/按钮背景
    "bg_muted": QColor(0xF2, 0xF2, 0xF7),          # 次级背景
    "bg_hover": QColor(0xE5, 0xE5, 0xEA),          # 悬停背景

    # 文字
    "text_primary": QColor(0x1D, 0x1D, 0x1F),      # 主文字
    "text_secondary": QColor(0x6E, 0x6E, 0x73),    # 次级文字
    "text_muted": QColor(0x8E, 0x8E, 0x93),        # 弱化文字

    # 边框/分隔
    "border": QColor(0xE5, 0xE5, 0xEA),             # 主边框
    "border_light": QColor(0xD1, 0xD1, 0xD6),       # 淡边框/分隔线

    # 主色（Apple 系统蓝）
    "primary": QColor(0x00, 0x7A, 0xFF),
    "primary_hover": QColor(0x00, 0x62, 0xCC),

    # 状态色
    "success": QColor(0x34, 0xC7, 0x59),
    "warning": QColor(0xFF, 0x95, 0x00),
    "error": QColor(0xFF, 0x3B, 0x30),
}

KEY_DISPLAY = {
    "mouse_left": "鼠标左键", "mouse_right": "鼠标右键", "mouse_middle": "鼠标中键",
    "mouse4": "鼠标侧键1", "mouse5": "鼠标侧键2",
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win",
    "lctrl": "左Ctrl", "rctrl": "右Ctrl", "lalt": "左Alt", "ralt": "右Alt",
    "lshift": "左Shift", "rshift": "右Shift",
    "left": "←", "right": "→", "up": "↑", "down": "↓",
    "space": "空格", "enter": "回车", "tab": "Tab", "backspace": "退格",
}

PANEL_ROWS = [
    [("toggle_mode", "跟随演奏")],
    [("toggle_visible", "隐藏窗口")],
    [("next_song", "下一首")],
    [("toggle_adjust", "调整窗口")],
    [("toggle_play", "从头重来")],
    [("toggle_panel", "面板穿透")],
    [("editor", "添加曲谱")],
    [("quit", "退出程序")],
]

REC_WRAP = 16
REC_KEEP = 200
REC_KEEP_WANT = 120


def combo_state(pref):
    chars = set(pref)
    if "#" in chars:
        if "b" in chars:
            return 4
        if "^" in chars:
            return 5
        return 2
    if "b" in chars and "^" in chars:
        return 3
    if "b" in chars:
        return 1
    if "^" in chars:
        return 3
    return 0
