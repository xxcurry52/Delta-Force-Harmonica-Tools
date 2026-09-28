import json
import os
import sys

from .constants import DEFAULT_NOTE_KEYS, KEY_DISPLAY

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DEFAULT_SONGS_DIR = os.path.join(BASE_DIR, "songs")
SONGS_DIR = DEFAULT_SONGS_DIR

SAMPLE_SONGS = {
    "小星星.txt": """BPM=90
TITLE=小星星
// 数字 = 简谱音高，与游戏按键一一对应：1=z 2=x 3=c 4=v 5=b 6=n 7=m 8=,
// 每个音 1 拍，后面的 - 表示延长 1 拍；| 只是小节线，随便写
1 1 5 5 6 6 5 -
4 4 3 3 2 2 1 -
5 5 4 4 3 3 2 -
5 5 4 4 3 3 2 -
1 1 5 5 6 6 5 -
4 4 3 3 2 2 1 -
""",
    "欢乐颂.txt": """BPM=100
TITLE=欢乐颂
3 3 4 5 | 5 4 3 2 | 1 1 2 3 | 3 - 2 -
3 3 4 5 | 5 4 3 2 | 1 1 2 3 | 2 - 1 -
""",
    "音域与变调练习.txt": """BPM=80
TITLE=音域与变调练习
// 本音（白）：八个键全弹一遍，8 = 高音1（, 键）
1 2 3 4 5 6 7 8 -
// 降调（绿）：长按鼠标左键再弹
b1 b2 b3 b4 b5 b6 b7 -
// 半音（紫）：长按鼠标中键再弹
#1 #2 #3 #4 #5 #6 #7 -
// 升调（蓝）：长按鼠标右键再弹
^1 ^2 ^3 ^4 ^5 ^6 ^7 -
// 半音+降调（黄）：同时按住鼠标中键 + 左键再弹
#b1 #b2 #b3 #b4 #b5 #b6 #b7 -
// 半音+升调（红）：同时按住鼠标中键 + 右键再弹
#^1 #^2 #^3 #^4 #^5 #^6 #^7 -
""",
    "父亲.txt": """TITLE=父亲（筷子兄弟）
// =====================================================================
// 《父亲》键盘谱（由网络流传的键盘谱图片逐音转写 · 已按原图色块逐音复核）
//
// 记号对照：
//   z x c v b n m = 简谱 1 2 3 4 5 6 7
//   前缀 ^  = 按住鼠标右键（原图写作"高音"，浅蓝色块）
//   无前缀  = 不按鼠标    （原图写作"中音"，橙色块）
//
// ⚠️ 复核说明：原图的"高音"标记有两处线索——数字头上的小圆点、以及
//    按键块的底色。这张谱里少数音"漏打了圆点"，但按键块是蓝色的，
//    本文件一律以【按键块底色】为准（蓝=高音）。
// =====================================================================

// 1. 总是向你索取 却不曾说谢谢你
^1 5 ^1 ^3 ^4 ^3 | ^2 ^1 ^1 5 ^1 ^2 ^3

// 2. 直到长大以后 才懂得你不容易
^1 5 ^1 ^3 ^4 ^3 | ^2 ^1 ^3 ^2 ^2 ^1 ^1

// 3. 每次离开总是 装作轻松的样子
^1 5 ^1 ^3 ^4 ^3 | ^2 ^1 ^6 ^5 ^5 ^4 ^3

// 4. 微笑着说回去吧 转身泪湿眼底
^1 5 ^1 ^3 ^4 ^3 | ^2 ^1 ^3 ^2 ^2 ^1 ^1

// 5. 多想和从前一样 牵你温暖手掌
^1 6 ^6 ^6 ^5 ^3 | ^3 ^3 ^4 ^5 ^1 ^5 ^3

// 6. 可是你不在我身旁 托清风捎去安康
^1 7 6 ^6 ^6 ^7 ^5 | ^5 ^5 ^6 ^5 ^4 ^3 ^3 ^2

// 7. 时光时光慢些吧 不要再让你变老了
6 7 ^1 ^1 ^1 ^1 7 | 6 7 7 7 7 ^3 ^2 ^1

// 8. 我愿用我一切 换岁月长留
6 7 ^1 ^1 ^1 ^1 ^1 | 7 6 7 5

// 9. 一生要强的爸爸 我能为你做些什么
6 7 ^1 ^1 ^1 ^1 7 | 6 7 7 7 7 ^3 7 ^1

// 10. 微不足道的关心 收下吧
6 7 ^1 ^1 ^1 ^3 ^2 7 6 6
""",
    "See You Again.txt": """BPM=90
TITLE=See You Again
// 全谱面 9 段（^ 前缀 = 高音，按住鼠标右键弹）
// ===== 第一段 =====
5 ^2 ^1 5 | ^1 ^2 ^3 ^2 ^1 ^2 | 5 ^2 ^1 5
// ===== 第二段 =====
1 3 5 6 5 | 1 2 2 1 3
// ===== 第三段 =====
3 5 6 7 6 5 3 2 2 1 2 2 3 1
// ===== 第四段 =====
1 3 5 6 5 | 1 2 2 1 3
// ===== 第五段 =====
2 3 5 6 ^1 ^2 ^3 ^2 ^1 6 ^1 ^2 ^2 ^1 ^1
// ===== 第六段 =====
6 ^1 ^2 ^2 ^1 ^1
// ===== 第七段 =====
^7 ^6 ^5 | ^7 ^6 ^7 ^6 ^5 ^3
// ===== 第八段 =====
5 6 ^1 ^2 ^3 | ^2 ^3 | ^2 ^3
// ===== 第九段 =====
^2 ^3 ^5 | ^3 ^2 ^1 6 ^1 ^2 ^1
""",
}

DEFAULT_CONFIG = {
    "opacity": 0.94,
    "bg_alpha": 235,
    "hit_line_offset": 10,
    "panel_width": 168,
    "panel_interactive": True,
    "songs_dir": "",
    "loop": True,
    "keyboard_monitor": True,
    "leader_strict_modifier": False,
    "mod_change_note": True,
    "mode": "classic",
    "leader_block_scale": 1.0,
    "leader_hold_until_release": True,
    "follow_speed": 200.0,
    "follow_lead": 2.0,
    "follow_window": 0.20,
    "hold_min_seconds": 0.15,
    "hold_grace": 0.20,
    "follow_rate": 1.0,
    "countdown_seconds": 3,
    "note_keys": list(DEFAULT_NOTE_KEYS),
    "modifier_keys": {
        "降调": ["mouse_left"],
        "半音": ["mouse_middle"],
        "升调": ["mouse_right"],
    },
    "hotkeys": {
        "toggle_visible": "shift+f6",
        "next_song": "shift+f7",
        "toggle_adjust": "shift+f8",
        "toggle_play": "shift+f9",
        "toggle_panel": "shift+f10",
        "editor": "shift+f11",
        "toggle_record": "shift+f12",
        "save_song": "shift+f3",
        "toggle_mode": "shift+f5",
        "rate_up": "shift+up",
        "rate_down": "shift+down",
        "quit": "ctrl+alt+q",
    },
}


def resolve_songs_dir(cfg=None):
    raw = ""
    if isinstance(cfg, dict):
        raw = str(cfg.get("songs_dir") or "").strip()
    if not raw:
        return DEFAULT_SONGS_DIR
    if not os.path.isabs(raw):
        raw = os.path.join(BASE_DIR, raw)
    return os.path.normpath(raw)


def apply_songs_dir(cfg=None):
    global SONGS_DIR
    SONGS_DIR = resolve_songs_dir(cfg)
    try:
        os.makedirs(SONGS_DIR, exist_ok=True)
    except Exception as e:
        print("[曲谱] 无法创建曲谱文件夹:", SONGS_DIR, e)
        SONGS_DIR = DEFAULT_SONGS_DIR
    return SONGS_DIR


def is_default_songs_dir(path):
    try:
        return os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(DEFAULT_SONGS_DIR))
    except Exception:
        return False


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            for section in ("hotkeys", "modifier_keys"):
                if isinstance(cfg.get(section), dict):
                    for k, v in DEFAULT_CONFIG[section].items():
                        cfg[section].setdefault(k, v)
            return cfg
        except Exception as e:
            print("[config] 读取失败，使用默认配置:", e)
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(updates):
    """写入 config.json（带防抖：合并多次快速调用，延迟写盘）。

    非冻结环境下用 QTimer 延迟 1 秒合并写入；冻结（exe）环境退回即时写。
    """
    try:
        data = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data.update(updates)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[config] 保存失败:", e)


def ensure_data_files():
    if not os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("[config] 写入失败:", e)
    try:
        os.makedirs(SONGS_DIR, exist_ok=True)
        for name, text in SAMPLE_SONGS.items():
            path = os.path.join(SONGS_DIR, name)
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
    except Exception as e:
        print("[songs] 写入失败:", e)


def format_combo(combo):
    out = []
    for part in str(combo).split("+"):
        p = part.strip().lower()
        if not p:
            continue
        if p in KEY_DISPLAY:
            out.append(KEY_DISPLAY[p])
        else:
            out.append(p.upper() if len(p) <= 2 else p.title())
    return "+".join(out)


def format_hotkey(combo, joiner="/"):
    parts = str(combo).split("|")
    return joiner.join(format_combo(p) for p in parts if p.strip())


def hotkey_text(cfg, action, joiner="/"):
    combo = cfg.get("hotkeys", {}).get(action, "")
    return format_hotkey(combo, joiner) if combo else ""


# 防抖保存：用模块级 QTimer 延迟合并写盘，避免拖窗口/调倍速时频繁 I/O
_pending_saves = {}
_save_timer = None


def schedule_save(updates):
    """延迟 1 秒合并写入 config.json，避免高频调用（拖窗口、连续调倍速）。"""
    global _save_timer, _pending_saves
    _pending_saves.update(updates)
    if _save_timer is not None:
        try:
            _save_timer.stop()
        except Exception:
            pass
    try:
        from PySide6.QtCore import QTimer
        if _save_timer is None:
            _save_timer = QTimer()
            _save_timer.setSingleShot(True)
            _save_timer.timeout.connect(_flush_saves)
        _save_timer.setInterval(1000)
        _save_timer.start()
    except Exception:
        save_config(_pending_saves)
        _pending_saves.clear()


def _flush_saves():
    global _pending_saves
    if _pending_saves:
        save_config(_pending_saves)
        _pending_saves.clear()


def flush_pending_saves():
    """退出前调用，确保缓冲的 config 更新落盘。"""
    global _pending_saves
    if _pending_saves:
        save_config(_pending_saves)
        _pending_saves.clear()
