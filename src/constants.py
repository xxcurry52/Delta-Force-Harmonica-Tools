from PySide6.QtGui import QColor

KEY_LABELS = ["z", "x", "c", "v", "b", "n", "m", ","]
DEFAULT_NOTE_KEYS = ["z", "x", "c", "v", "b", "n", "m", "comma"]
KEY_INDEX = {k: i for i, k in enumerate("zxcvbnm,")}

STATE_STYLE = [
    dict(fill=QColor(0xF0, 0xEA, 0xDB), text=QColor(0x3B, 0x37, 0x2E)),
    dict(fill=QColor(0x22, 0xC5, 0x5E), text=QColor(0xFF, 0xFF, 0xFF)),
    dict(fill=QColor(0xA8, 0x55, 0xF7), text=QColor(0xFF, 0xFF, 0xFF)),
    dict(fill=QColor(0x4C, 0x8D, 0xF6), text=QColor(0xFF, 0xFF, 0xFF)),
    dict(fill=QColor(0xF2, 0xC5, 0x1F), text=QColor(0x3B, 0x37, 0x2E)),
    dict(fill=QColor(0xE0, 0x3E, 0x3E), text=QColor(0xFF, 0xFF, 0xFF)),
]

STRIP_COLORS = [QColor(0xFF, 0xFF, 0xFF), QColor(0x22, 0xC5, 0x5E),
                QColor(0xA8, 0x55, 0xF7), QColor(0x4C, 0x8D, 0xF6),
                QColor(0xF2, 0xC5, 0x1F), QColor(0xE0, 0x3E, 0x3E)]

STATE_TOKEN_PREFIX = {0: "", 1: "b", 2: "#", 3: "^", 4: "#b", 5: "#^"}
PREFIX_CHARS = "b#^"
MOD_ROLES = ["降调", "半音", "升调"]
STATE_NAMES = ["本音", "降调", "半音", "升调", "半音+降调", "半音+升调"]
STATE_SHORT = ["本音", "降调", "半音", "升调", "半+降", "半+升"]
STATE_MODS = [[], ["降调"], ["半音"], ["升调"], ["半音", "降调"], ["半音", "升调"]]
CHIP_LAYOUT = [1, 0, 3, 4, 2, 5]

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
    [("editor", "✚ 添加曲谱")],
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
