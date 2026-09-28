import math
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import (QColor, QPainter, QPen, QFont, QFontMetrics, QPainterPath,
                           QBrush, QRadialGradient)
from PySide6.QtWidgets import QApplication, QWidget

from .constants import (KEY_LABELS, DEFAULT_NOTE_KEYS, STATE_STYLE, STRIP_COLORS,
                         THEME, STATE_MODS, MOD_ROLES, REC_KEEP, REC_KEEP_WANT,
                         combo_state)
from .config import (CONFIG_PATH, SONGS_DIR, DEFAULT_SONGS_DIR, schedule_save,
                      flush_pending_saves, hotkey_text)
from .song_parser import (load_songs, parse_song, note_token)
from .winapi import (vk_of, vk_name, GWL_EXSTYLE, WS_EX_LAYERED,
                      WS_EX_TRANSPARENT, WS_EX_NOACTIVATE, user32, force_topmost)
from .utils import square_plate_corner


class Overlay(QWidget):
    close_requested = Signal()

    def __init__(self, cfg, songs, panel=None):
        super().__init__(None,
                         Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.cfg = cfg
        self.songs = songs
        self.song_idx = 0
        self.panel = panel
        self.sub = None

        self.cursor = 0
        self.slide = None
        self.ghost = None
        self.finished_at = None
        self.held_press = None

        self.mode = cfg.get("mode", "classic")
        if self.mode not in ("classic", "follow"):
            self.mode = "classic"
        self.follow_state = "idle"
        self.follow_t0 = None
        self.follow_next = 0
        self._paused = False
        self._pause_time = None
        self.follow_missed = set()
        self.follow_hold = None
        self.follow_fade = set()
        self.key_down = {}
        self.countdown_deadline = None

        self.flashes = {}
        self.impacts = []
        self.wrong = {}
        self.held_mods = []
        self.adjust_mode = False
        self._drag = None
        self._resize_dir = None
        self._resize_start_geo = None
        self._toast = None

        self.editor = None
        self._editor_was_visible = False
        self.recording = False
        self.rec_log = []
        self.rec_count = 0

        self.note_vks = []
        keys = cfg.get("note_keys") or DEFAULT_NOTE_KEYS
        for i in range(8):
            name = keys[i] if i < len(keys) else DEFAULT_NOTE_KEYS[i]
            self.note_vks.append(vk_of(name) or vk_of(DEFAULT_NOTE_KEYS[i]))

        self.mod_vk = {}
        for role, names in cfg["modifier_keys"].items():
            vks = [v for v in (vk_of(n) for n in names) if v]
            self.mod_vk[role] = vks or [0x11]
        self.hotkey_vks = {}
        for action, combo in cfg["hotkeys"].items():
            combos = []
            for alt in str(combo).split("|"):
                vks = tuple(v for v in (vk_of(p) for p in alt.split("+")) if v)
                if vks:
                    combos.append(vks)
            if combos:
                self.hotkey_vks[action] = combos
        self._watched = (set(self.note_vks)
                         | {v for vs in self.mod_vk.values() for v in vs}
                         | {v for combos in self.hotkey_vks.values() for c in combos for v in c})
        self._prev = {}
        self._prev_mod = {}
        self._prev_state = 0
        self._prev_hot = {}
        self._input_ok = bool(cfg.get("keyboard_monitor", True))
        self._last_detect = None

        self._dirty = True
        self._prev_input_snapshot = None

        self.setWindowTitle("口琴可视化曲谱")
        self.setAttribute(Qt.WA_TranslucentBackground)
        scr = QApplication.primaryScreen().availableGeometry()
        geo = cfg.get("geometry")
        if (isinstance(geo, (list, tuple)) and len(geo) == 4
                and 300 < geo[2] <= scr.width() and 360 <= geo[3] <= scr.height()):
            self.setGeometry(int(geo[0]), int(geo[1]), int(geo[2]), int(geo[3]))
        else:
            self.resize(760, 560)
            self.move(scr.center().x() - 380, scr.bottom() - 580)
        self.setWindowOpacity(float(cfg.get("opacity", 0.94)))

        self._last = time.monotonic()
        self._panel_next = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    @property
    def song(self):
        return self.songs[self.song_idx]

    def select_song(self, idx):
        self.song_idx = max(0, min(idx, len(self.songs) - 1))
        self.reset_playback()
        self._say("曲谱：" + self.song.title)

    def reset_playback(self):
        self.cursor = 0
        self.slide = None
        self.ghost = None
        self.held_press = None
        self.finished_at = None
        self.flashes.clear()
        self.impacts.clear()
        self.wrong.clear()
        self.follow_state = "idle"
        self.follow_t0 = None
        self.follow_next = 0
        self._paused = False
        self._pause_time = None
        self.follow_missed.clear()
        self.follow_hold = None
        self.follow_fade.clear()
        self.countdown_deadline = None
        if self.panel:
            self.panel.ensure_visible()
        self._dirty = True

    def toggle_adjust(self):
        self.set_adjust_mode(not self.adjust_mode)

    def toggle_record(self):
        self.set_recording(not self.recording)

    def toggle_pause(self):
        if self.mode == "follow":
            if not self._paused and self.follow_state == "playing":
                self._paused = True
                self._pause_time = time.monotonic()
            elif self._paused:
                pause_dur = time.monotonic() - self._pause_time
                if self.follow_t0 is not None:
                    self.follow_t0 += pause_dur
                if self.countdown_deadline is not None:
                    self.countdown_deadline += pause_dur
                self._paused = False
                self._pause_time = None
        else:
            self.reset_playback()
        self._dirty = True

    def reload_songs(self, select_title=None):
        songs = load_songs()
        if not songs:
            return
        want = select_title or (self.song.title if self.songs else None)
        self.songs = songs
        idx = 0
        for i, s in enumerate(songs):
            if s.title == want:
                idx = i
                break
        self.song_idx = idx
        self.reset_playback()
        if self.panel:
            self.panel.song_scroll = 0
            self.panel.ensure_visible()
            self.panel.update()
        self._say("曲谱已更新：%s（共 %d 首）" % (self.song.title, len(songs)))

    def _panel_width(self):
        w = float(self.width())
        want = float(self.cfg.get("panel_width", 168))
        return max(126.0, min(want, w * 0.46))

    def sync_panel(self):
        pass

    def moveEvent(self, e):
        self.sync_panel()
        super().moveEvent(e)

    def resizeEvent(self, e):
        self.sync_panel()
        self._dirty = True
        super().resizeEvent(e)

    def _apply_clickthrough(self):
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_NOACTIVATE
            # 不再整窗穿透——需要边框和拖拽条可交互
            # 只在完全隐藏时穿透
            if not self.isVisible():
                style |= WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            force_topmost(hwnd)
        except Exception as e:
            print("[overlay] 设置窗口样式失败:", e)

    def _force_topmost(self):
        """周期性强制置顶，防止被游戏窗口覆盖"""
        try:
            hwnd = int(self.winId())
            force_topmost(hwnd)
            if self.panel and self.panel.isVisible():
                phwnd = int(self.panel.winId())
                force_topmost(phwnd)
            if self.sub and self.sub.isVisible():
                shwnd = int(self.sub.winId())
                force_topmost(shwnd)
        except Exception:
            pass

    def set_adjust_mode(self, on):
        self.adjust_mode = on
        self._apply_clickthrough()
        if on:
            self.show()
            self.raise_()
        if self.panel:
            self.panel.raise_()
        self._dirty = True

    def _poll_input(self):
        if not self._input_ok:
            return False
        st = {vk: bool(user32.GetAsyncKeyState(vk) & 0x8000) for vk in self._watched}
        pressed_now = set()
        changed = False

        for role, vks in self.mod_vk.items():
            any_down = any(st.get(v, False) for v in vks)
            if any_down and not self._prev_mod.get(role, False):
                if role in self.held_mods:
                    self.held_mods.remove(role)
                self.held_mods.append(role)
                changed = True
            elif not any_down and self._prev_mod.get(role, False):
                if role in self.held_mods:
                    self.held_mods.remove(role)
                changed = True
            self._prev_mod[role] = any_down

        for i, vk in enumerate(self.note_vks):
            down, was = st.get(vk, False), self._prev.get(vk, False)
            if was and not down:
                self._on_note_release(i)
                changed = True

        for i, vk in enumerate(self.note_vks):
            down, was = st.get(vk, False), self._prev.get(vk, False)
            self.key_down[i] = down
            if down and not was:
                pressed_now.add(i)
                changed = True
                if self.recording:
                    self._record_note(i)
                else:
                    self._on_note_press(i)

        self._mod_change_onsets(pressed_now)

        mono = time.monotonic()
        for action, combos in self.hotkey_vks.items():
            all_down = any(all(st.get(v, False) for v in c) for c in combos)
            if all_down and not self._prev_hot.get(action, False):
                self.do_action(action)
                changed = True
            self._prev_hot[action] = all_down

        for vk, down in st.items():
            if down and not self._prev.get(vk, False):
                self._last_detect = (mono, vk_name(vk))
                break

        self._prev = st
        return changed

    def _mod_change_onsets(self, just_pressed):
        st_now = self.current_state()
        prev, self._prev_state = self._prev_state, st_now
        if st_now == prev:
            return
        if not self.cfg.get("mod_change_note", True):
            return
        for ch in sorted(self.key_down):
            if not self.key_down.get(ch, False) or ch in just_pressed:
                continue
            if self.recording:
                self._record_note(ch)
            elif self.mode != "follow":
                self._on_note_press(ch)

    def _mod_ok(self, state):
        need = STATE_MODS[state] if 0 <= state < len(STATE_MODS) else []
        return all(role in self.held_mods for role in need)

    def current_state(self):
        held = [r for r in self.held_mods if r in MOD_ROLES]
        if not held:
            return 0
        hset = set(held)
        if "半音" in hset:
            dirs = [r for r in reversed(held) if r in ("降调", "升调")]
            if "降调" in hset and "升调" in hset:
                return 4 if (dirs and dirs[0] == "降调") else 5
            if "降调" in hset:
                return 4
            if "升调" in hset:
                return 5
            return 2
        return MOD_ROLES.index(held[-1]) + 1

    def _on_note_press(self, ch):
        if not 0 <= ch <= 7:
            return
        now = time.monotonic()
        if self.mode == "follow":
            self._follow_press(ch, now)
            return
        while True:
            if self.finished_at is not None or self.cursor >= len(self.song.notes):
                return
            note = self.song.notes[self.cursor]
            if note[2] != ch:
                self.wrong[ch] = now
                return
            if self.cfg.get("leader_strict_modifier", False) and not self._mod_ok(note[3]):
                self.wrong[ch] = now
                return
            if self.held_press is None:
                break
            self._release_held(now)

        self.flashes[ch] = (now, note[3])
        self.impacts.append((now, ch, note[3]))
        if self.cfg.get("leader_hold_until_release", True):
            self.held_press = (now, ch, note[3], note[1])
        else:
            self._finish_note(now, ch, note[3], note[1])

    def _finish_note(self, now, ch, state, dur):
        h = self._leader_unit() * dur
        self.ghost = (now, ch, state, h)
        self.slide = (now, h + 6.0)
        self.cursor += 1
        if self.cursor >= len(self.song.notes):
            self.finished_at = now

    def _release_held(self, now=None):
        hp = self.held_press
        if hp is None:
            return
        self.held_press = None
        if now is None:
            now = time.monotonic()
        _, ch, state, dur = hp
        self._finish_note(now, ch, state, dur)

    def _on_note_release(self, ch):
        if self.mode == "follow":
            return
        hp = self.held_press
        if hp is not None and hp[1] == ch:
            self._release_held()

    def _follow_spb(self):
        return 60.0 / max(1.0, self.song.bpm)

    def _follow_lead(self):
        return float(self.cfg.get("follow_lead", 2.0))

    def _follow_rate(self):
        try:
            r = float(self.cfg.get("follow_rate", 1.0))
        except Exception:
            r = 1.0
        return max(0.2, min(2.0, r))

    def change_rate(self, delta):
        cur = self._follow_rate()
        new = round(max(0.2, min(2.0, cur + delta)), 2)
        if abs(new - cur) < 1e-9:
            self._say("倍速已经到%s（%d%%）"
                      % ("上限" if delta > 0 else "下限", round(new * 100)))
            return new
        now = time.monotonic()
        if self.follow_state == "playing" and self.follow_t0 is not None:
            play = (now - self.follow_t0) * cur
            self.follow_t0 = now - play / new
        self.cfg["follow_rate"] = new
        self._save_config({"follow_rate": new})
        self._say("跟随倍速 %d%%" % round(new * 100))
        if self.panel:
            self.panel.update()
        if self.sub:
            self.sub.update()
        self._dirty = True
        return new

    def _follow_window(self):
        return float(self.cfg.get("follow_window", 0.20)) * self._follow_rate()

    def _follow_play_time(self, now):
        if self.follow_state == "playing" and self.follow_t0 is not None:
            return (now - self.follow_t0) * self._follow_rate() - self._follow_lead()
        if self.song and self.song.notes:
            return self.song.notes[0][0] * self._follow_spb() - self._follow_lead()
        return -self._follow_lead()

    def _follow_press(self, ch, now):
        notes = self.song.notes
        if self.follow_state == "idle":
            if not notes:
                return
            n = notes[0]
            if n[2] != ch:
                self.wrong[ch] = now
                return
            secs = int(self.cfg.get("countdown_seconds", 3))
            self.follow_state = "countdown"
            self.countdown_deadline = now + secs
            self._say("准备就绪，%d 秒后开始…" % secs)
            self._dirty = True
            return
        if self.follow_state == "countdown":
            return
        if self.follow_state != "playing":
            return
        if self.follow_hold is not None:
            if ch != self.follow_hold["ch"]:
                self.wrong[ch] = now
            return
        if self.follow_next >= len(notes):
            return
        n = notes[self.follow_next]
        if n[2] != ch:
            self.wrong[ch] = now
            return
        hit = n[0] * self._follow_spb()
        play = self._follow_play_time(now)
        if abs(play - hit) > self._follow_window():
            self.wrong[ch] = now
            return
        self.flashes[ch] = (now, n[3])
        self.follow_hold = {"idx": self.follow_next, "ch": ch, "state": n[3],
                            "start": play, "dur": float(n[1]), "released": None}
        self._dirty = True

    def _hold_min_seconds(self):
        try:
            return float(self.cfg.get("hold_min_seconds", 0.15))
        except Exception:
            return 0.15

    def _hold_total(self, dur):
        return max(float(dur) * self._follow_spb(),
                   self._hold_min_seconds() * self._follow_rate())

    def _follow_check_done(self, now):
        if self.follow_next >= len(self.song.notes):
            self.follow_state = "done"
            self.finished_at = now

    def _follow_hold_progress(self, now):
        h = self.follow_hold
        if not h:
            return 0.0
        total = max(0.05, self._hold_total(h["dur"]))
        return max(0.0, min(1.0, (self._follow_play_time(now) - h["start"]) / total))

    def _follow_hold_tick(self, now):
        h = self.follow_hold
        if not h:
            return False
        total = max(0.05, self._hold_total(h["dur"]))
        play = self._follow_play_time(now)
        held = self.key_down.get(h["ch"], False) or not self._input_ok

        if held:
            h["released"] = None
        elif h["released"] is None:
            h["released"] = now
        elif now - h["released"] > float(self.cfg.get("hold_grace", 0.20)):
            self.follow_fade.add(h["idx"])
            self.follow_next = h["idx"] + 1
            self.follow_hold = None
            self.wrong[h["ch"]] = now
            self._say("没按住，漏过")
            self._follow_check_done(now)
            return True

        if play - h["start"] >= total:
            self.flashes[h["ch"]] = (now, h["state"])
            self.impacts.append((now, h["ch"], h["state"]))
            self.follow_next = h["idx"] + 1
            self.follow_hold = None
            self._say("完成！")
            self._follow_check_done(now)
            return True
        return False

    def _follow_auto_catch(self, now):
        if self.follow_hold is not None:
            return False
        if self.follow_next >= len(self.song.notes):
            return False
        n = self.song.notes[self.follow_next]
        if not self.key_down.get(n[2], False):
            return False
        play = self._follow_play_time(now)
        hit = n[0] * self._follow_spb()
        if abs(play - hit) > self._follow_window():
            return False
        self.flashes[n[2]] = (now, n[3])
        self.follow_hold = {"idx": self.follow_next, "ch": n[2], "state": n[3],
                            "start": play, "dur": float(n[1]), "released": None}
        return True

    def _follow_advance_missed(self, now):
        spb = self._follow_spb()
        play = self._follow_play_time(now)
        win = self._follow_window()
        while self.follow_next < len(self.song.notes):
            if self.follow_hold is not None and self.follow_hold["idx"] == self.follow_next:
                break
            n = self.song.notes[self.follow_next]
            if n[0] * spb + win < play:
                self.follow_missed.add(self.follow_next)
                self.follow_fade.add(self.follow_next)
                self.follow_next += 1
                if self.follow_next >= len(self.song.notes):
                    self.follow_state = "done"
                    self.finished_at = now
            else:
                break

    def set_recording(self, on):
        on = bool(on)
        if on and not self._input_ok:
            self._say("输入读取已在 config.json 里关闭，无法录音")
            return
        if on == self.recording:
            return
        self.recording = on
        if on:
            self.rec_log = []
            self.rec_count = 0
            self._say("● 录音中：按顺序弹一遍（z x c v b n m ,），%s 结束" % self.hk("toggle_record"))
        else:
            n = len(self.editor.recorded_tokens()) if self.editor else 0
            self._say("录音结束：共 %d 个音 ｜ 按 %s 直接保存，或 %s 打开编辑器"
                      % (n, self.hk("save_song"), self.hk("editor")))
        if self.editor:
            self.editor.set_recording_ui(on)
        if self.panel:
            self.panel.update()
        if self.sub:
            self.sub.update()
        self._dirty = True

    def _record_note(self, ch):
        st = self.current_state()
        self.flashes[ch] = (time.monotonic(), st)
        self.rec_log.append((ch, st))
        self.rec_count += 1
        if len(self.rec_log) > REC_KEEP:
            del self.rec_log[:-REC_KEEP_WANT]
        if self.editor:
            self.editor.rec_append(note_token(ch, st))

    def truncate_rec(self, n):
        if not self.recording:
            return
        n = max(0, int(n))
        drop = self.rec_count - n
        if drop > 0 and self.rec_log:
            cut = max(0, len(self.rec_log) - drop)
            for ch, _st in self.rec_log[cut:]:
                self.flashes.pop(ch, None)
            del self.rec_log[cut:]
        self.rec_count = n
        self._dirty = True
        if self.panel:
            self.panel.update()

    def toggle_editor(self):
        if not self.editor:
            return
        if self.editor.isVisible():
            self.editor.hide()
        else:
            self.editor.show_editor()

    def do_action(self, action):
        if action == "toggle_adjust":
            self.set_adjust_mode(not self.adjust_mode)
            self._say("调整模式：拖动 / 缩放对齐，再按一次锁定" if self.adjust_mode
                      else "已锁定窗口")
        elif action == "toggle_visible":
            if self.isVisible():
                ev = bool(self.editor and self.editor.isVisible())
                self._editor_was_visible = ev
                if ev:
                    self.editor.hide()
                self.hide()
                if self.panel:
                    self.panel.hide()
                if self.sub:
                    self.sub.hide()
            else:
                self.show()
                self.raise_()
                if self.panel:
                    self.panel.show()
                    self.panel.raise_()
                if self.sub:
                    self.sub.show()
                    self.sub.raise_()
                if self._editor_was_visible and self.editor:
                    self.editor.show()
                    self.editor.raise_()
                self._editor_was_visible = False
        elif action == "toggle_play":
            self.reset_playback()
            self._say("从头重来")
        elif action == "toggle_mode":
            self.mode = "classic" if self.mode == "follow" else "follow"
            self.reset_playback()
            self._save_config({"mode": self.mode})
            if self.sub:
                self.sub.update()
            if self.mode == "follow":
                self._say("已切到【跟随演奏】：弹对第一个音开始，之后音符按时值下落")
            else:
                self._say("已切到【经典模式】：音符堆叠，按顺序逐个消除")
        elif action == "next_song":
            self.select_song((self.song_idx + 1) % len(self.songs))
        elif action == "toggle_panel":
            on = not self.cfg.get("panel_interactive", True)
            self.cfg["panel_interactive"] = on
            if self.panel:
                self.panel.apply_style()
            self._save_config({"panel_interactive": on})
            self._say("面板可点击" if on else "面板已穿透（按 %s 恢复）" % self.hk("toggle_panel"))
        elif action == "editor":
            self.toggle_editor()
        elif action == "toggle_record":
            self.set_recording(not self.recording)
        elif action == "save_song":
            if self.editor:
                self.editor.save_quick()
        elif action in ("rate_up", "rate_down"):
            d = 0.1 if action == "rate_up" else -0.1
            if self._sub_kind() == "rate":
                self.change_rate(d)
            else:
                self.change_block_scale(d)
        elif action == "quit":
            self.save_geometry()
            flush_pending_saves()
            QApplication.quit()
        if self.panel:
            self.panel.update()
        self._dirty = True

    def _say(self, text):
        self._toast = (time.monotonic(), text)
        self._dirty = True

    def hk(self, action, joiner="/"):
        return hotkey_text(self.cfg, action, joiner)

    def _has_active_animations(self):
        return bool(self.slide or self.ghost or self.held_press
                    or self.flashes or self.impacts or self.wrong
                    or self._toast or self.finished_at)

    def _tick(self):
        mono = time.monotonic()
        self._last = mono
        input_changed = self._poll_input()

        # 每 2 秒强制置顶，防止被游戏窗口覆盖
        if not hasattr(self, '_topmost_timer') or mono - getattr(self, '_last_topmost', 0) > 2.0:
            self._last_topmost = mono
            self._force_topmost()

        if self.mode == "follow" and not self._paused:
            if self.follow_state == "countdown" and self.countdown_deadline is not None:
                if mono >= self.countdown_deadline:
                    first = (self.song.notes[0][0] * self._follow_spb()
                             if self.song.notes else 0.0)
                    self.follow_t0 = mono - first / self._follow_rate()
                    self.follow_state = "playing"
                    self._say("开始！")
                self._dirty = True
            elif self.follow_state == "playing":
                self._follow_hold_tick(mono)
                self._follow_advance_missed(mono)
                self._follow_auto_catch(mono)
                self._dirty = True

        if self.finished_at and self.cfg.get("loop", True) and mono - self.finished_at > 1.2:
            self.reset_playback()

        if self.recording:
            self._dirty = True

        if self.adjust_mode:
            self._dirty = True

        if input_changed or self._has_active_animations() or self._dirty:
            self.update()
            self._dirty = False

        if self.panel and self.panel.isVisible() and mono >= self._panel_next:
            self._panel_next = mono + 0.08
            self.panel.update()

    def _note_geometry(self):
        w = float(self.width())
        pad = 8.0
        x0 = pad
        ch_w = max(12.0, (w - x0 - pad) / 8.0)
        return x0, ch_w, pad

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())

        # 全屏音符区（不再有左侧面板偏移）
        pad = 8.0
        x0 = pad
        ch_w = max(12.0, (w - x0 - pad) / 8.0)

        # 字体大小：Accessible & Ethical 风格 — 大字体高可读性
        font_title = 13
        font_legend = 11
        font_key = 14

        # 背景：浅色半透明 — Accessible & Ethical 风格
        bg_alpha = int(self.cfg.get("bg_alpha", 235))
        bg = QColor(239, 246, 255)  # #EFF6FF
        bg.setAlpha(bg_alpha)
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w, h), 10, 10)

        # 顶部拖拽条
        bar_h = 36.0
        bar_bg = QColor(30, 64, 175)  # #1E40AF primary blue
        bar_bg.setAlpha(240)
        p.setBrush(bar_bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w, bar_h), 10, 10)
        # 底部直角覆盖
        p.drawRect(QRectF(0, bar_h - 10, w, 10))

        # 拖拽条文字
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Microsoft YaHei UI", font_title, QFont.Bold))
        p.drawText(QRectF(14, 0, w - 100, bar_h), Qt.AlignVCenter | Qt.AlignLeft,
                   "口琴可视化 · 拖动这里移动")

        # 关闭按钮
        close_x = w - 24
        close_y = bar_h / 2
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Consolas", 16, QFont.Bold))
        p.drawText(QRectF(close_x - 12, 0, 24, bar_h), Qt.AlignCenter, "×")

        # 音调图例（拖拽条下方）
        leg_y = bar_h + 4
        leg_h = 24.0
        legends = [
            (STATE_STYLE[0]["fill"], "本音"),
            (STATE_STYLE[1]["fill"], "降调"),
            (STATE_STYLE[2]["fill"], "半音"),
            (STATE_STYLE[3]["fill"], "升调"),
        ]
        lx = 12.0
        for color, label in legends:
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(lx + 6, leg_y + leg_h / 2), 5, 5)
            p.setPen(QColor(30, 58, 138))  # #1E3A8A foreground
            p.setFont(QFont("Microsoft YaHei UI", font_legend, QFont.Medium))
            p.drawText(QRectF(lx + 14, leg_y, 56, leg_h), Qt.AlignVCenter | Qt.AlignLeft, label)
            lx += 72

        # 按键提示标签（右上角）
        p.setPen(QColor(71, 85, 105))  # #475569 muted foreground
        p.setFont(QFont("Microsoft YaHei UI", font_legend))
        p.drawText(QRectF(w - 220, leg_y, 208, leg_h), Qt.AlignVCenter | Qt.AlignRight,
                   "键位：z x c v b n m ,")

        # 音符区域
        label_h = 24.0
        hit_y = h - label_h - float(self.cfg.get("hit_line_offset", 10))

        # 通道背景线（极淡）
        p.setPen(QPen(QColor(30, 64, 175, 20), 1))
        for i in range(1, 8):
            x = x0 + i * ch_w
            p.drawLine(QPointF(x, bar_h + leg_h + 4), QPointF(x, hit_y - 2))

        # 判定线 — 高对比度
        p.setPen(QPen(QColor(30, 64, 175), 3))
        p.drawLine(QPointF(x0, hit_y), QPointF(w - pad, hit_y))

        # 底部按键标签
        p.setPen(QColor(30, 58, 138))  # #1E3A8A
        p.setFont(QFont("Consolas", font_key, QFont.Bold))
        for ch in range(8):
            p.drawText(QRectF(x0 + ch * ch_w, hit_y + 4, ch_w, 20),
                       Qt.AlignCenter, KEY_LABELS[ch])

        # 绘制音符
        p.save()
        clip_top = bar_h + leg_h + 4
        p.setClipRect(QRectF(x0 - 3, clip_top, w - x0 + 3, hit_y - clip_top))
        if self.recording:
            self._draw_recording(p, x0, ch_w, hit_y)
        elif self.mode == "follow":
            self._draw_follow(p, x0, ch_w, hit_y)
        else:
            self._draw_leader(p, x0, ch_w, hit_y)
        p.restore()

        # 调整模式提示
        if self.adjust_mode:
            p.setPen(QPen(QColor(240, 163, 60, 200), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 10, 10)

    def _draw_wrong(self, p, x0, ch_w, hit_y):
        now = time.monotonic()
        for ch, t0 in list(self.wrong.items()):
            age = now - t0
            if age > 0.3:
                self.wrong.pop(ch, None)
                continue
            c = QColor(0xE2, 0x3B, 0x3B)
            c.setAlpha(int(190 * (1 - age / 0.3)))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x0 + ch * ch_w + 3, hit_y - 9, ch_w - 6, 14), 4, 4)

    def _draw_block(self, p, rect, state, ch, highlight=False):
        style = STATE_STYLE[state]
        r = min(8.0, rect.height() / 2.0, rect.width() / 2.0)
        p.setPen(Qt.NoPen)
        p.setBrush(style["fill"])
        p.drawRoundedRect(rect, r, r)
        if highlight:
            p.setPen(QPen(QColor(0xF5, 0xA6, 0x23), 3))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), r + 2, r + 2)
            p.setPen(Qt.NoPen)
        fsize = int(max(12.0, min(rect.width() * 0.55, rect.height() * 0.45, 32.0)))
        p.setPen(style["text"])
        p.setFont(QFont("Consolas", fsize, QFont.Bold))
        p.drawText(rect, Qt.AlignCenter, KEY_LABELS[ch])

    def _draw_block_held(self, p, rect, state, ch, held):
        style = STATE_STYLE[state]
        r = min(8.0, rect.height() / 2.0, rect.width() / 2.0)
        fill = QColor(style["fill"])
        fill.setAlpha(100)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(rect, r, r)
        p.setPen(QPen(QColor(style["fill"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), r + 1, r + 1)
        fsize = int(max(12.0, min(rect.width() * 0.55, rect.height() * 0.45, 32.0)))
        txt = QColor(style["text"])
        txt.setAlpha(160)
        p.setPen(txt)
        p.setFont(QFont("Consolas", fsize, QFont.Bold))
        p.drawText(rect, Qt.AlignCenter, KEY_LABELS[ch])

    def _leader_scale(self):
        try:
            k = float(self.cfg.get("leader_block_scale", 1.0))
        except Exception:
            k = 1.0
        return max(0.5, min(2.0, k))

    def change_block_scale(self, delta):
        cur = self._leader_scale()
        new = round(max(0.5, min(2.0, cur + delta)), 2)
        if abs(new - cur) < 1e-9:
            self._say("方块长度已经到%s（%d%%）"
                      % ("上限" if delta > 0 else "下限", round(new * 100)))
            return new
        self.cfg["leader_block_scale"] = new
        self._save_config({"leader_block_scale": new})
        self._say("方块长度 %d%%" % round(new * 100))
        if self.panel:
            self.panel.update()
        if self.sub:
            self.sub.update()
        self._dirty = True
        return new

    def _sub_kind(self):
        return "rate" if (self.mode == "follow" and not self.recording) else "block"

    def _leader_unit(self):
        return max(22.0, min(36.0, self.height() * 0.06)) * self._leader_scale()

    def _draw_leader(self, p, x0, ch_w, hit_y):
        unit = self._leader_unit()
        gap = 4.0
        shift = 0.0
        if self.slide:
            t0, dist = self.slide
            prog = min(1.0, (time.monotonic() - t0) / 0.16)
            ease = 1 - (1 - prog) ** 3
            shift = -dist * (1 - ease)
            if prog >= 1.0:
                self.slide = None

        y = hit_y - 4.0 + shift
        now = time.monotonic()
        hold = self.held_press
        for idx, (start, dur, ch, st) in enumerate(self.song.notes[self.cursor:]):
            bh = unit * dur
            rect = QRectF(x0 + ch * ch_w + ch_w * 0.1, y - bh, ch_w * 0.80, bh)
            if rect.bottom() < 0:
                break
            if idx == 0 and hold is not None and hold[1] == ch:
                self._draw_block_held(p, rect, st, ch, now - hold[0])
            else:
                self._draw_block(p, rect, st, ch, highlight=(idx == 0))
            y -= bh + gap

        if self.finished_at is not None:
            p.setPen(QColor(22, 163, 74))
            p.setFont(QFont("Microsoft YaHei UI", 13, QFont.Bold))
            p.drawText(QRectF(x0, hit_y * 0.4, self.width() - x0, 24),
                       Qt.AlignCenter, "完成")

    def _draw_recording(self, p, x0, ch_w, hit_y):
        w = float(self.width())
        now = time.monotonic()

        pulse = 0.55 + 0.45 * abs(((now * 1.6) % 2.0) - 1.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0xE2, 0x4B, 0x4B, int(180 + 75 * pulse)))
        p.drawEllipse(QPointF(x0 + 10.0, 14.0), 4.0, 4.0)
        p.setPen(QColor(30, 58, 138))
        p.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        p.drawText(QRectF(x0 + 20.0, 6.0, w - x0 - 30.0, 20.0),
                   Qt.AlignLeft | Qt.AlignVCenter, "录音中 · 已录 %d 音 · %s 结束"
                   % (self.rec_count, self.hk("toggle_record")))

        unit = 30.0 * self._leader_scale()
        gap = 4.0
        avail = max(60.0, w - x0 - 16.0)
        cap = max(1, int((avail + gap) // (unit + gap)))
        tail = self.rec_log[-cap:] if self.rec_log else []
        ty = hit_y - unit - 12.0
        bx = w - 8.0 - len(tail) * (unit + gap) + gap
        for i, (ch, st) in enumerate(tail):
            r = QRectF(bx + i * (unit + gap), ty, unit, unit)
            style = STATE_STYLE[st]
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(style["fill"]))
            p.drawRoundedRect(r, 6, 6)
            p.setPen(style["text"])
            p.setFont(QFont("Consolas", int(max(8.0, min(unit * 0.4, 18.0))), QFont.Bold))
            p.drawText(r, Qt.AlignCenter, KEY_LABELS[ch])

        if not self.rec_count:
            p.setPen(QColor(71, 85, 105))
            p.setFont(QFont("Microsoft YaHei UI", 10))
            p.drawText(QRectF(x0, ty - 30.0, avail, 20.0), Qt.AlignCenter,
                       "按 z x c v b n m , 开始录音")

    def _draw_follow(self, p, x0, ch_w, hit_y):
        now = time.monotonic()
        song = self.song
        spb = self._follow_spb()
        speed = max(40.0, float(self.cfg.get("follow_speed", 200)))
        play = self._follow_play_time(now)
        w = float(self.width())

        draw_from = self.follow_next
        if self.follow_fade:
            draw_from = min(draw_from, min(self.follow_fade))
        for i in range(draw_from, len(song.notes)):
            start, dur, ch, st = song.notes[i]
            hit = start * spb
            y_end = hit_y - (hit - play) * speed
            bh = max(6.0, dur * spb * speed)
            y_start = y_end - bh
            if y_end < -4.0:
                continue
            if y_start > hit_y + 6.0:
                self.follow_fade.discard(i)
                continue
            rect = QRectF(x0 + ch * ch_w + ch_w * 0.1, y_start, ch_w * 0.80, bh)
            holding = bool(self.follow_hold and self.follow_hold["idx"] == i)
            if holding:
                p.save()
                p.setClipRect(QRectF(0.0, 0.0, w, hit_y))
            self._draw_block(p, rect, st, ch,
                             highlight=(i == self.follow_next and not holding))
            if holding:
                prog = self._follow_hold_progress(now)
                p.setPen(QPen(QColor(255, 255, 255, int(200 - 100 * prog)), 2))
                p.setBrush(Qt.NoBrush)
                rad = min(8.0, max(3.0, rect.width() / 2.0))
                p.drawRoundedRect(rect.adjusted(-1.0, -1.0, 1.0, 1.0), rad, rad)
                p.restore()
            if i in self.follow_fade or i in self.follow_missed:
                r = min(8.0, rect.height() / 2.0, rect.width() / 2.0)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 140))
                p.drawRoundedRect(rect, r, r)

        if self.follow_state == "idle":
            first = song.notes[0] if song.notes else None
            p.setPen(QColor(30, 64, 175))
            p.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
            p.drawText(QRectF(x0, hit_y * 0.35, w - x0, 24), Qt.AlignCenter,
                       "跟随模式")
            if first is not None:
                p.setPen(QColor(71, 85, 105))
                p.setFont(QFont("Microsoft YaHei UI", 10))
                p.drawText(QRectF(x0, hit_y * 0.35 + 24, w - x0, 20), Qt.AlignCenter,
                           "弹「%s」开始" % KEY_LABELS[first[2]])

        if self.follow_state == "countdown" and self.countdown_deadline is not None:
            remain = self.countdown_deadline - now
            n = max(1, int(math.ceil(remain)))
            p.setPen(QColor(30, 64, 175))
            p.setFont(QFont("Microsoft YaHei UI", 30, QFont.Bold))
            p.drawText(QRectF(x0, hit_y * 0.35, w - x0, 40), Qt.AlignCenter, str(n))

        if self.follow_state == "done":
            p.setPen(QColor(22, 163, 74))
            p.setFont(QFont("Microsoft YaHei UI", 13, QFont.Bold))
            p.drawText(QRectF(x0, hit_y * 0.4, w - x0, 24), Qt.AlignCenter,
                       "完成")

    def _draw_impacts(self, p, x0, ch_w, hit_y):
        now = time.monotonic()
        for it in list(self.impacts):
            t0, ch, st = it
            age = now - t0
            if age > 0.32:
                self.impacts.remove(it)
                continue
            k = age / 0.32
            base = QColor(STATE_STYLE[st]["fill"])
            cx = x0 + ch * ch_w + ch_w * 0.5
            cy = hit_y - 2.0
            max_r = ch_w * 0.62
            r = max_r * (0.35 + 0.65 * k)
            grad = QRadialGradient(cx, cy, max(1.0, r))
            inner = QColor(base); inner.setAlpha(int(150 * (1 - k)))
            outer = QColor(base); outer.setAlpha(0)
            grad.setColorAt(0.0, inner)
            grad.setColorAt(1.0, outer)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(cx, cy), r, r)
            ring = QColor(base); ring.setAlpha(int(110 * (1 - k)))
            p.setPen(QPen(ring, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)

    def _draw_strip(self, p, x0, w, hit_y):
        st = self.current_state()
        color = QColor(STRIP_COLORS[st])
        left, width = x0, w - x0 - 8.0
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(left, hit_y - 1.5, width, 3.0), 1.5, 1.5)

    def _draw_toast(self, p, x0, w):
        if not self._toast:
            return
        age = time.monotonic() - self._toast[0]
        if age >= 2.2:
            self._toast = None
            return
        alpha = max(0, min(255, int(255 * (1.0 if age < 1.6 else (2.2 - age) / 0.6))))
        text = self._toast[1]
        fm = QFontMetrics(QFont("Microsoft YaHei UI", 9))
        tw = min(float(fm.horizontalAdvance(text) + 24), max(80.0, w - x0 - 20.0))
        rect = QRectF(w - 10.0 - tw, 10.0, tw, 24.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(30, 64, 175, min(235, alpha)))
        p.drawRoundedRect(rect, 12, 12)
        p.setPen(QColor(0xFF, 0xFF, 0xFF, alpha))
        p.setFont(QFont("Microsoft YaHei UI", 9))
        p.drawText(rect, Qt.AlignCenter, fm.elidedText(text, Qt.ElideRight,
                                                       int(max(10.0, tw - 18.0))))

    def _draw_adjust_hint(self, p, x0, w, h, hit_y):
        if not self.adjust_mode:
            return
        p.setPen(QPen(QColor(0xF0, 0xA3, 0x3C, 200), 2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(2, 2, int(w - 4), int(h - 4))
        p.setPen(QColor(0xF0, 0xA3, 0x3C, 235))
        p.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        p.drawText(QRectF(x0, hit_y * 0.38, max(80.0, w - x0 - 8), 20), Qt.AlignHCenter,
                   "调整模式：拖动移动/缩放 · %s 锁定"
                   % self.hk("toggle_adjust"))

    def save_geometry(self):
        self._save_config({"geometry": [self.x(), self.y(), self.width(), self.height()]})

    def _save_config(self, updates):
        schedule_save(updates)

    def _edge_at(self, pos):
        m = 8
        w, h = self.width(), self.height()
        l, r = pos.x() <= m, pos.x() >= w - m
        t, b = pos.y() <= m, pos.y() >= h - m
        if l and t: return "lt"
        if r and t: return "rt"
        if l and b: return "lb"
        if r and b: return "rb"
        if l: return "l"
        if r: return "r"
        if t: return "t"
        if b: return "b"
        return None

    def _is_on_close(self, pos):
        return pos.x() >= self.width() - 36 and pos.y() <= 32.0

    def _is_in_title_bar(self, pos):
        return pos.y() <= 32.0 and not self._is_on_close(pos)

    def mousePressEvent(self, e):
        pos = e.position()
        if self._is_on_close(pos):
            self.close_requested.emit()
            return
        edge = self._edge_at(pos)
        if edge:
            self._resize_dir = edge
            self._resize_start_geo = self.geometry()
            self._drag_start = e.globalPosition().toPoint()
            return
        if self._is_in_title_bar(pos) or self.adjust_mode:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._resize_dir = None

    def mouseMoveEvent(self, e):
        g = e.globalPosition().toPoint()
        if self._resize_dir and self._resize_start_geo is not None:
            geo = self._resize_start_geo
            dx = g.x() - self._drag_start.x()
            dy = g.y() - self._drag_start.y()
            nx, ny, nw, nh = geo.x(), geo.y(), geo.width(), geo.height()
            d = self._resize_dir
            if "l" in d:
                nx = geo.x() + dx
                nw = geo.width() - dx
            if "r" in d:
                nw = geo.width() + dx
            if "t" in d:
                ny = geo.y() + dy
                nh = geo.height() - dy
            if "b" in d:
                nh = geo.height() + dy
            if nw >= 300 and nh >= 150:
                self.setGeometry(nx, ny, nw, nh)
        elif self._drag is not None:
            self.move(g - self._drag)
        else:
            edge = self._edge_at(e.position())
            cursors = {"l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
                       "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
                       "lt": Qt.SizeFDiagCursor, "rb": Qt.SizeFDiagCursor,
                       "rt": Qt.SizeBDiagCursor, "lb": Qt.SizeBDiagCursor}
            if edge:
                self.setCursor(cursors[edge])
            elif self._is_in_title_bar(e.position()):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        if self._drag is not None or self._resize_dir:
            self.save_geometry()
        self._drag = None
        self._resize_dir = None
        self._resize_start_geo = None
