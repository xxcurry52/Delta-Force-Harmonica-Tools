import ctypes

from .constants import KEY_DISPLAY

VK_NAMES = {
    "mouse_left": 0x01, "mouse_right": 0x02, "mouse_middle": 0x04,
    "mouse4": 0x05, "mouse5": 0x06, "xbutton1": 0x05, "xbutton2": 0x06,
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "lctrl": 0xA2, "rctrl": 0xA3, "lalt": 0xA4, "ralt": 0xA5,
    "lshift": 0xA6, "rshift": 0xA7, "lwin": 0x5B, "rwin": 0x5C,
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "backspace": 0x08,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "comma": 0xBC, "period": 0xBE, "slash": 0xBF, "semicolon": 0xBA,
    "minus": 0xBD, "plus": 0xBB,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}

CHAR_NAMES = {0xBC: "，", 0xBE: "。", 0xBF: "/", 0xBA: "；", 0xBD: "-", 0xBB: "="}

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000

user32 = ctypes.windll.user32


def vk_of(name):
    name = str(name).strip().lower()
    if name in VK_NAMES:
        return VK_NAMES[name]
    if name == ",":
        return 0xBC
    if name == ".":
        return 0xBE
    if len(name) == 1 and name.isalnum():
        return ord(name.upper())
    return None


def vk_name(vk):
    if vk in CHAR_NAMES:
        return CHAR_NAMES[vk]
    for k, v in VK_NAMES.items():
        if v == vk and k not in ("xbutton1", "xbutton2", "period"):
            return KEY_DISPLAY.get(k, k.upper() if len(k) <= 2 else k.title())
    return "0x%02X" % vk
