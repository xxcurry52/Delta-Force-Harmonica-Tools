import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .config import load_config, apply_songs_dir, ensure_data_files, flush_pending_saves
from .song_parser import load_songs
from .constants import KEY_LABELS, PANEL_ROWS
from .overlay import Overlay
from .panel import PanelWindow
from .sub_panel import SubPanel
from .editor import SongEditor
from .config import hotkey_text

SAFETY_NOTE = ("[安全声明] 不安装键盘钩子、不模拟按键、不读写游戏内存、不注入游戏进程、不联网；"
               "仅用 GetAsyncKeyState 读取按键状态并绘制普通置顶分层窗口。")


def _run_selftest():
    _c0 = load_config()
    apply_songs_dir(_c0)
    ensure_data_files()
    c = load_config()
    ss = load_songs()
    for s in ss:
        print("曲谱: %-16s BPM %-4s 音符数 %-3d 时长 %.1f 拍" % (
            s.title, round(s.bpm), len(s.notes), s.total_beats))
    from .winapi import vk_of
    from .constants import DEFAULT_NOTE_KEYS
    print("通道按键:", " ".join(KEY_LABELS),
          "| config.note_keys:", c.get("note_keys"),
          "| VK:", ["0x%02X" % (vk_of(k) or 0) for k in (c.get("note_keys") or DEFAULT_NOTE_KEYS)])
    print("热键:", ", ".join("%s=%s" % (k, v) for k, v in c["hotkeys"].items()))
    print("面板按钮:", ", ".join(a for row in PANEL_ROWS for a, _ in row))
    print("跟随倍速:", c.get("follow_rate"),
          "| 最短按住:", c.get("hold_min_seconds"), "秒",
          "| 经典方块长度:", c.get("leader_block_scale"),
          "| 切音高算新音:", c.get("mod_change_note"),
          "| 经典按住才消:", c.get("leader_hold_until_release"))
    print("keyboard_monitor:", c.get("keyboard_monitor"),
          "| panel_width:", c.get("panel_width"),
          "| panel_interactive:", c.get("panel_interactive"))
    from .config import SONGS_DIR, is_default_songs_dir
    print("曲谱文件夹:", SONGS_DIR, "(默认)" if is_default_songs_dir(SONGS_DIR) else "(自定义)")
    sys.exit(0)


def main():
    if "--selftest" in sys.argv:
        _run_selftest()
    cfg = load_config()
    apply_songs_dir(cfg)
    ensure_data_files()
    songs = load_songs()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    ov = Overlay(cfg, songs)
    panel = PanelWindow(ov)
    ov.panel = panel
    sub = SubPanel(ov)
    ov.sub = sub
    editor = SongEditor(ov)
    ov.editor = editor
    ov.sync_panel()
    ov.show()
    panel.show()
    panel.raise_()
    sub.show()
    sub.raise_()
    from .config import schedule_save
    schedule_save({"hotkeys": cfg["hotkeys"]})
    QTimer.singleShot(200, ov._apply_clickthrough)
    QTimer.singleShot(220, panel.apply_style)
    QTimer.singleShot(240, sub.apply_style)
    print(SAFETY_NOTE)
    print("按键：%s" % " ".join(KEY_LABELS))
    print("热键（都要按住 Shift，避免和游戏里的 F 键抢键）：")
    for act, name in (("toggle_visible", "显示/隐藏全部窗口"), ("next_song", "换下一首"),
                      ("toggle_adjust", "锁定/调整窗口"), ("toggle_play", "从头重来"),
                      ("toggle_panel", "面板穿透"), ("editor", "曲谱编辑器"),
                      ("toggle_record", "开始/结束录音"), ("save_song", "保存曲谱"),
                      ("toggle_mode", "切换 经典/跟随演奏 模式"),
                      ("rate_up", "跟随倍速 +10%（最快 200%）／ 经典模式方块 +10%（最长 200%）"),
                      ("rate_down", "跟随倍速 -10%（最慢 20%）／ 经典模式方块 -10%（最短 50%）"),
                      ("quit", "退出")):
        print("  %-20s %s" % (hotkey_text(cfg, act, " / "), name))
    print("也可以直接用鼠标点击窗口左侧面板上的按钮。")
    if not cfg.get("keyboard_monitor", True):
        print("[提示] keyboard_monitor=false：当前不读取任何键鼠输入，热键与灯带均不生效。")
    ret = app.exec()
    flush_pending_saves()
    sys.exit(ret)
