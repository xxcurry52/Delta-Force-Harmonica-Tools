import os
import shutil
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

from .config import (load_config, apply_songs_dir, ensure_data_files,
                     flush_pending_saves, save_config, hotkey_text,
                     resolve_songs_dir)
from .song_parser import load_songs
from .constants import KEY_LABELS, PANEL_ROWS
from .overlay import Overlay
from .panel import PanelWindow
from .sub_panel import SubPanel
from .editor import SongEditor
from .main_window import MainWindow
from .settings_dialog import SettingsDialog

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
    app.setQuitOnLastWindowClosed(True)

    # 主窗口（启动首屏）
    mw = MainWindow(cfg, songs)
    mw.show()
    mw.raise_()

    # 叠加层组件（延迟创建，按需显示）
    ov = Overlay(cfg, songs)
    panel = PanelWindow(ov)
    ov.panel = panel
    sub = SubPanel(ov)
    ov.sub = sub
    editor = SongEditor(ov)
    ov.editor = editor
    ov.sync_panel()

    # 默认隐藏叠加层
    ov.hide()
    panel.hide()
    sub.hide()

    _overlay_visible = [False]

    def show_overlay():
        if not _overlay_visible[0]:
            _overlay_visible[0] = True
            ov.show()
            ov.raise_()
            QTimer.singleShot(200, ov._apply_clickthrough)
            ov._force_topmost()

    def hide_overlay():
        if _overlay_visible[0]:
            _overlay_visible[0] = False
            ov.hide()

    def toggle_overlay():
        if _overlay_visible[0]:
            hide_overlay()
        else:
            show_overlay()

    def on_overlay_requested():
        toggle_overlay()

    def on_play():
        idx = mw.song_idx
        if 0 <= idx < len(songs):
            ov.select_song(idx)
        if not _overlay_visible[0]:
            show_overlay()

    def on_pause():
        ov.toggle_pause()

    def on_song_selected():
        idx = mw.song_idx
        if 0 <= idx < len(songs):
            ov.select_song(idx)

    def on_next():
        idx = mw.song_idx
        if 0 <= idx < len(songs):
            ov.select_song(idx)

    def on_prev():
        idx = mw.song_idx
        if 0 <= idx < len(songs):
            ov.select_song(idx)

    def on_mode_changed(mode):
        ov.mode = mode
        ov.cfg["mode"] = mode

    def on_rate_changed(rate):
        ov.cfg["follow_rate"] = rate
        ov._save_config({"follow_rate": rate})

    def on_block_changed(scale):
        ov.cfg["leader_block_scale"] = scale
        ov._save_config({"leader_block_scale": scale})
        if ov.sub:
            ov.sub.update()

    def on_opacity_changed(opacity):
        ov.cfg["opacity"] = opacity
        ov.setWindowOpacity(opacity)
        ov._save_config({"opacity": opacity})

    def on_bg_alpha_changed(val):
        ov.cfg["bg_alpha"] = val
        ov._save_config({"bg_alpha": val})
        ov._dirty = True
        ov.update()

    def on_adjust():
        if _overlay_visible[0]:
            ov.toggle_adjust()

    def on_passthrough():
        cur = ov.cfg.get("panel_interactive", True)
        ov.cfg["panel_interactive"] = not cur
        ov._save_config({"panel_interactive": not cur})
        if ov.panel:
            ov.panel.apply_style()
        ov._apply_clickthrough()

    def on_editor():
        if ov.editor:
            ov.editor.show()
            ov.editor.raise_()

    def on_record():
        ov.toggle_record()

    def on_save_song():
        if ov.editor:
            ov.editor.save_current()

    def on_add_song():
        songs_dir = resolve_songs_dir(cfg)
        path, _ = QFileDialog.getOpenFileName(
            mw, "选择曲谱文件", "", "曲谱文件 (*.txt);;所有文件 (*)")
        if not path:
            return
        dest = os.path.join(songs_dir, os.path.basename(path))
        shutil.copy2(path, dest)
        new_songs = load_songs()
        mw.songs = new_songs
        ov.songs = new_songs
        mw._refresh_song_list()
        ov.reload_songs()
        mw.status_label.setText("已添加曲谱：%s" % os.path.basename(path))

    def on_quit():
        hide_overlay()
        flush_pending_saves()
        app.quit()

    def on_settings():
        dlg = SettingsDialog(cfg, mw)
        dlg.settings_changed.connect(on_settings_applied)
        dlg.exec()

    def on_settings_applied(new_cfg):
        cfg.clear()
        cfg.update(new_cfg)
        save_config(cfg)
        ov.cfg = cfg
        ov._apply_clickthrough()
        ov._force_topmost()
        if _overlay_visible[0]:
            ov._force_topmost()
        mw.status_label.setText("设置已保存")

    mw.overlay_requested.connect(on_overlay_requested)
    mw.play_requested.connect(on_play)
    mw.next_song_requested.connect(on_next)
    mw.prev_song_requested.connect(on_prev)
    mw.song_selected.connect(on_song_selected)
    mw.pause_requested.connect(on_pause)
    mw.add_song_requested.connect(on_add_song)
    mw.mode_changed.connect(on_mode_changed)
    mw.quit_requested.connect(on_quit)
    mw.settings_requested.connect(on_settings)
    mw.rate_changed.connect(on_rate_changed)
    mw.block_scale_changed.connect(on_block_changed)
    mw.opacity_changed.connect(on_opacity_changed)
    mw.bg_alpha_changed.connect(on_bg_alpha_changed)
    mw.adjust_requested.connect(on_adjust)
    mw.panel_passthrough_requested.connect(on_passthrough)
    mw.editor_requested.connect(on_editor)
    mw.record_requested.connect(on_record)
    mw.save_song_requested.connect(on_save_song)

    # 悬浮窗 × 关闭按钮
    ov.close_requested.connect(hide_overlay)

    # 叠加层热键仍然生效（即使主窗口在前台）
    from .config import schedule_save
    schedule_save({"hotkeys": cfg["hotkeys"]})

    print(SAFETY_NOTE)
    print("按键：%s" % " ".join(KEY_LABELS))
    print("启动模式：主窗口已显示，点击「显示悬浮窗」或按热键弹出叠加层")
    ret = app.exec()
    flush_pending_saves()
    sys.exit(ret)
