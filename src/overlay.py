import math
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (QColor, QPainter, QPen, QFont, QFontMetrics, QPainterPath,
                           QBrush, QRadialGradient)
from PySide6.QtWidgets import QApplication, QWidget

from .constants import (KEY_LABELS, DEFAULT_NOTE_KEYS, STATE_STYLE, STRIP_COLORS,
                         STATE_MODS, MOD_ROLES, REC_KEEP, REC_KEEP_WANT,
                         combo_state)
from .config import (CONFIG_PATH, SONGS_DIR, DEFAULT_SONGS_DIR, schedule_save,
                      flush_pending_saves, hotkey_text)
from .song_parser import (load_songs, parse_song, note_token)
from .winapi import (vk_of, vk_name, GWL_EXSTYLE, WS_EX_LAYERED,
                      WS_EX_TRANSPARENT, WS_EX_NOACTIVATE, user32)
from .utils import square_plate_corner


class Overlay(QWidget):
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
        self.follow_missed.clear()
        self.follow_hold = None
        self.follow_fade.clear()
        self.countdown_deadline = None
        if self.panel:
            self.panel.ensure_visible()
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
        if not self.panel:
            return
        self.panel.setGeometry(self.x(), self.y(),
                               int(self._panel_width()), self.height())
        if self.sub:
            self.sub.sync_geometry()

    def moveEvent(self, e):
        self.sync_panel()
        super().moveEvent(e)

    def resizeEvent(self, e):
        self.sync_panel()
        super().resizeEvent(e)

    def _apply_clickthrough(self):
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_NOACTIVATE
            if self.adjust_mode:
                style &= ~WS_EX_TRANSPARENT
            else:
                style |= WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as e:
            print("[overlay] 设置窗口样式失败:", e)

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

        if self.mode == "follow":
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
        x0 = self._panel_width() + pad
        ch_w = max(12.0, (w - x0 - pad) / 8.0)
        return x0, ch_w, pad

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        x0, ch_w, pad = self._note_geometry()
        hit_y = h - float(self.cfg.get("hit_line_offset", 10))

        plate = QPainterPath()
        plate.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 12, 12)
        if self.sub is not None and self.sub.isVisible():
            if self.sub.y() >= self.y() + self.height() - 4:
                plate = square_plate_corner(plate, w, h, "bl")
            elif self.sub.y() + self.sub.height() <= self.y() + 4:
                plate = square_plate_corner(plate, w, h, "tl")
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(QColor(24, 22, 19, int(self.cfg.get("bg_alpha", 150))))
        p.drawPath(plate)

        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        for i in range(1, 8):
            x = x0 + i * ch_w
            p.drawLine(QPointF(x, 8), QPointF(x, hit_y))

        p.save()
        p.setClipRect(QRectF(x0 - 3, 0, w - x0 + 3, hit_y))
        if self.recording:
            self._draw_recording(p, x0, ch_w, hit_y)
        elif self.mode == "follow":
            self._draw_follow(p, x0, ch_w, hit_y)
        else:
            self._draw_leader(p, x0, ch_w, hit_y)
        p.restore()

        self._draw_strip(p, x0, w, hit_y)
        self._draw_wrong(p, x0, ch_w, hit_y)
        self._draw_toast(p, x0, w)
        self._draw_adjust_hint(p, x0, w, h, hit_y)

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
        r = min(12.0, rect.height() / 2.0, rect.width() / 2.0)
        p.setPen(Qt.NoPen)
        p.setBrush(style["fill"])
        p.drawRoundedRect(rect, r, r)
        if rect.height() > 10.0:
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            p.drawLine(QPointF(rect.left() + r, rect.top() + 1.0),
                       QPointF(rect.right() - r, rect.top() + 1.0))
        if highlight:
            p.setPen(QPen(QColor(255, 255, 255, 235), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), r + 2, r + 2)
            p.setPen(Qt.NoPen)
        fsize = int(max(10.0, min(rect.width() * 0.62, rect.height() * 0.5, 30.0)))
        p.setPen(style["text"])
        p.setFont(QFont("Consolas", fsize, QFont.Bold))
        p.drawText(rect, Qt.AlignCenter, KEY_LABELS[ch])

    def _draw_block_held(self, p, rect, state, ch, held):
        style = STATE_STYLE[state]
        r = min(12.0, rect.height() / 2.0, rect.width() / 2.0)
        base = QColor(style["fill"])

        fill = QColor(base)
        fill.setAlpha(105)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(rect, r, r)

        k = abs(((held * 0.9) % 2.0) - 1.0)
        ring = QColor(base)
        ring.setAlpha(int(110 + 130 * k))
        p.setPen(QPen(ring, 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(-1.5, -1.5, 1.5, 1.5), r + 1.5, r + 1.5)

        if rect.height() > 12.0:
            span = rect.height() - 6.0
            yy = rect.bottom() - 3.0 - span * k
            band = QColor(255, 255, 255, int(70 + 90 * k))
            p.setPen(QPen(band, 2.0, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(rect.left() + 3.0, yy), QPointF(rect.right() - 3.0, yy))

        fsize = int(max(10.0, min(rect.width() * 0.62, rect.height() * 0.5, 30.0)))
        txt = QColor(style["text"])
        txt.setAlpha(170)
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
        gap = 6.0
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
            rect = QRectF(x0 + ch * ch_w + ch_w * 0.22, y - bh, ch_w * 0.56, bh)
            if rect.bottom() < 0:
                break
            if idx == 0 and hold is not None and hold[1] == ch:
                self._draw_block_held(p, rect, st, ch, now - hold[0])
            else:
                self._draw_block(p, rect, st, ch, highlight=(idx == 0))
            y -= bh + gap

        if self.ghost:
            t0, ch, st, gh = self.ghost
            age = time.monotonic() - t0
            if age > 0.24:
                self.ghost = None
            else:
                k = age / 0.24
                fill = QColor(STATE_STYLE[st]["fill"])
                fill.setAlpha(int(180 * (1 - k)))
                p.setPen(Qt.NoPen)
                p.setBrush(fill)
                bw = ch_w * 0.56
                bx = x0 + ch * ch_w + ch_w * 0.22
                p.drawRoundedRect(QRectF(bx, hit_y - 4 - gh * (1 - k), bw, gh * (1 - k)),
                                  min(12.0, gh / 2), min(12.0, gh / 2))

        now = time.monotonic()
        for ch, (t0, st) in list(self.flashes.items()):
            age = now - t0
            if age > 0.35:
                self.flashes.pop(ch, None)
                continue
            c = QColor(STATE_STYLE[st]["fill"])
            c.setAlpha(int(150 * (1 - age / 0.35)))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x0 + ch * ch_w + 2, hit_y - 5, ch_w - 4, 10), 4, 4)

        self._draw_impacts(p, x0, ch_w, hit_y)

        if self.finished_at is not None:
            p.setPen(QColor(255, 255, 255, 220))
            p.setFont(QFont("Microsoft YaHei UI", 14, QFont.DemiBold))
            p.drawText(QRectF(x0, hit_y * 0.42, self.width() - x0, 30),
                       Qt.AlignCenter, "演奏完成")

    def _draw_recording(self, p, x0, ch_w, hit_y):
        w = float(self.width())
        now = time.monotonic()

        pulse = 0.55 + 0.45 * abs(((now * 1.6) % 2.0) - 1.0)
        p.setPen(Qt.NoPen)
        top = 14.0
        p.setBrush(QColor(255, 255, 255, 26))
        p.drawRoundedRect(QRectF(x0, top, w - x0 - 8.0, 62.0), 10, 10)
        p.setBrush(QColor(0xE2, 0x4B, 0x4B, int(60 + 195 * pulse)))
        p.drawEllipse(QPointF(x0 + 22.0, top + 21.0), 6.0, 6.0)
        p.setPen(QColor(255, 255, 255, 240))
        p.setFont(QFont("Microsoft YaHei UI", 12, QFont.DemiBold))
        p.drawText(QRectF(x0 + 36.0, top + 8.0, w - x0 - 50.0, 26.0),
                   Qt.AlignLeft | Qt.AlignVCenter, "录音中")
        p.setPen(QColor(255, 255, 255, 175))
        p.setFont(QFont("Microsoft YaHei UI", 9))
        p.drawText(QRectF(x0 + 12.0, top + 34.0, w - x0 - 24.0, 22.0),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   "按顺序弹一遍按键（z x c v b n m ,）· 鼠标左=绿 中=紫 右=蓝 中+左=黄 中+右=红 · "
                   "已录 %d 个音 · %s 结束" % (self.rec_count, self.hk("toggle_record")))

        unit = 30.0 * self._leader_scale()
        gap = 4.0
        avail = max(60.0, w - x0 - 16.0)
        cap = max(1, int((avail + gap) // (unit + gap)))
        tail = self.rec_log[-cap:] if self.rec_log else []
        ty = hit_y - unit - 16.0
        bx = w - 8.0 - len(tail) * (unit + gap) + gap
        for i, (ch, st) in enumerate(tail):
            r = QRectF(bx + i * (unit + gap), ty, unit, unit)
            style = STATE_STYLE[st]
            p.setPen(QPen(QColor(255, 255, 255, 90), 1))
            p.setBrush(QColor(style["fill"]))
            p.drawRoundedRect(r, 8, 8)
            p.setPen(QColor(style["text"]))
            p.setFont(QFont("Microsoft YaHei UI",
                            int(max(8.0, min(unit * 0.34, 22.0))), QFont.DemiBold))
            p.drawText(r, Qt.AlignCenter, KEY_LABELS[ch])

        for ch, (t0, st) in list(self.flashes.items()):
            age = now - t0
            if age > 0.35:
                self.flashes.pop(ch, None)
                continue
            c = QColor(STATE_STYLE[st]["fill"])
            c.setAlpha(int(170 * (1 - age / 0.35)))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x0 + ch * ch_w + 2, hit_y - 5, ch_w - 4, 10), 4, 4)

        if not self.rec_count:
            p.setPen(QColor(255, 255, 255, 120))
            p.setFont(QFont("Microsoft YaHei UI", 10))
            p.drawText(QRectF(x0, ty - 40.0, avail, 24.0), Qt.AlignCenter,
                       "还没有录到音… 直接按 z x c v b n m , 试试")

    def _draw_follow(self, p, x0, ch_w, hit_y):
        now = time.monotonic()
        song = self.song
        spb = self._follow_spb()
        speed = max(40.0, float(self.cfg.get("follow_speed", 200)))
        play = self._follow_play_time(now)
        w = float(self.width())

        p.setPen(QPen(QColor(255, 255, 255, 110), 1))
        p.drawLine(QPointF(x0, hit_y), QPointF(w - 8.0, hit_y))

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
            rect = QRectF(x0 + ch * ch_w + ch_w * 0.22, y_start, ch_w * 0.56, bh)
            holding = bool(self.follow_hold and self.follow_hold["idx"] == i)
            if holding:
                p.save()
                p.setClipRect(QRectF(0.0, 0.0, w, hit_y))
            self._draw_block(p, rect, st, ch,
                             highlight=(i == self.follow_next and not holding))
            if holding:
                prog = self._follow_hold_progress(now)
                p.setPen(QPen(QColor(255, 255, 255, int(210 - 110 * prog)), 2))
                p.setBrush(Qt.NoBrush)
                rad = min(12.0, max(3.0, rect.width() / 2.0))
                p.drawRoundedRect(rect.adjusted(-2.0, -2.0, 2.0, 2.0), rad, rad)
                p.restore()
                bw = max(4.0, ch_w * 0.56 * (1.0 - prog))
                c = QColor(STATE_STYLE[st]["fill"])
                c.setAlpha(180)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(x0 + ch * ch_w + (ch_w - bw) / 2.0,
                                         hit_y - 9.0, bw, 9.0), 4, 4)
            if i in self.follow_fade or i in self.follow_missed:
                r = min(12.0, rect.height() / 2.0, rect.width() / 2.0)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 150))
                p.drawRoundedRect(rect, r, r)

        self._draw_impacts(p, x0, ch_w, hit_y)

        if self.follow_state == "idle":
            first = song.notes[0] if song.notes else None
            p.setPen(QColor(255, 255, 255, 240))
            p.setFont(QFont("Microsoft YaHei UI", 13, QFont.DemiBold))
            p.drawText(QRectF(x0, hit_y * 0.30, w - x0, 30), Qt.AlignCenter,
                       "跟随演奏模式")
            p.setPen(QColor(255, 255, 255, 175))
            p.setFont(QFont("Microsoft YaHei UI", 10))
            if first is not None:
                p.drawText(QRectF(x0, hit_y * 0.30 + 30, w - x0, 24), Qt.AlignCenter,
                           "弹对第一个音「%s」开始" % KEY_LABELS[first[2]])
            p.drawText(QRectF(x0, hit_y * 0.30 + 54, w - x0, 24), Qt.AlignCenter,
                       "开始前倒计时 %d 秒 · 每个音都要按住直到被吃掉"
                       % int(self.cfg.get("countdown_seconds", 3)))

        if self.follow_state == "countdown" and self.countdown_deadline is not None:
            remain = self.countdown_deadline - now
            n = max(1, int(math.ceil(remain)))
            p.setPen(QColor(255, 255, 255, 235))
            p.setFont(QFont("Microsoft YaHei UI", 54, QFont.Bold))
            p.drawText(QRectF(x0, hit_y * 0.30, w - x0, 64), Qt.AlignCenter, str(n))
            p.setPen(QColor(255, 255, 255, 160))
            p.setFont(QFont("Microsoft YaHei UI", 11))
            p.drawText(QRectF(x0, hit_y * 0.30 + 66, w - x0, 24), Qt.AlignCenter,
                       "准备…")

        if self.follow_state == "done":
            p.setPen(QColor(255, 255, 255, 220))
            p.setFont(QFont("Microsoft YaHei UI", 14, QFont.DemiBold))
            p.drawText(QRectF(x0, hit_y * 0.42, w - x0, 30), Qt.AlignCenter,
                       "演奏完成")

        rate = self._follow_rate()
        p.setPen(QColor(255, 255, 255, 205 if abs(rate - 1.0) > 1e-9 else 95))
        p.setFont(QFont("Microsoft YaHei UI", 10, QFont.DemiBold))
        p.drawText(QRectF(x0, 6.0, w - x0 - 10.0, 18.0),
                   Qt.AlignRight | Qt.AlignVCenter, "倍速 %d%%" % round(rate * 100))

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
        glow = QColor(color)
        glow.setAlpha(70)
        p.setBrush(glow)
        p.drawRoundedRect(QRectF(left, hit_y - 5.0, width, 12.0), 6, 6)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(left, hit_y - 2.0, width, 4.0), 2, 2)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(QRectF(left, hit_y + 3.0, width, 3.0), 1.5, 1.5)

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
        p.setBrush(QColor(18, 16, 14, min(205, alpha)))
        p.drawRoundedRect(rect, 12, 12)
        p.setPen(QColor(0xFF, 0xE0, 0x9A, alpha))
        p.setFont(QFont("Microsoft YaHei UI", 9))
        p.drawText(rect, Qt.AlignCenter, fm.elidedText(text, Qt.ElideRight,
                                                       int(max(10.0, tw - 18.0))))

    def _draw_adjust_hint(self, p, x0, w, h, hit_y):
        if not self.adjust_mode:
            return
        p.setPen(QPen(QColor(0xF0, 0xA3, 0x3C, 200), 2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 12, 12)
        p.setPen(QColor(0xF0, 0xA3, 0x3C, 235))
        p.setFont(QFont("Microsoft YaHei UI", 11))
        p.drawText(QRectF(x0, hit_y * 0.38, max(80.0, w - x0 - 8), 24), Qt.AlignHCenter,
                   "调整模式：拖动移动 · 拖边缘缩放 · 让 8 条竖线对准琴键、灯带贴住琴键上沿 · %s 锁定"
                   % self.hk("toggle_adjust"))

    def save_geometry(self):
        self._save_config({"geometry": [self.x(), self.y(), self.width(), self.height()]})

    def _save_config(self, updates):
        schedule_save(updates)

    def _edge_at(self, pos):
        m = 10
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

    def mousePressEvent(self, e):
        if not self.adjust_mode:
            return
        pos = e.position()
        self._resize_dir = self._edge_at(pos)
        g = e.globalPosition().toPoint()
        self._drag = g if self._resize_dir else g - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if not self.adjust_mode:
            return
        g = e.globalPosition().toPoint()
        if self._drag is None:
            edge = self._edge_at(e.position())
            cursors = {"l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
                       "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
                       "lt": Qt.SizeFDiagCursor, "rb": Qt.SizeFDiagCursor,
                       "rt": Qt.SizeBDiagCursor, "lb": Qt.SizeBDiagCursor}
            self.setCursor(cursors.get(edge, Qt.ArrowCursor))
            return
        if self._resize_dir:
            geo = self.frameGeometry()
            nx, ny, nw, nh = geo.x(), geo.y(), geo.width(), geo.height()
            d = self._resize_dir
            if "l" in d:
                dx = g.x() - self._drag.x()
                nx, nw = geo.x() + dx, geo.width() - dx
            if "r" in d:
                nw = geo.width() + (g.x() - self._drag.x())
            if "t" in d:
                dy = g.y() - self._drag.y()
                ny, nh = geo.y() + dy, geo.height() - dy
            if "b" in d:
                nh = geo.height() + (g.y() - self._drag.y())
            if nw >= 420 and nh >= 360:
                self.setGeometry(nx, ny, nw, nh)
            self._drag = g
        else:
            self.move(g - self._drag)

    def mouseReleaseEvent(self, e):
        if self.adjust_mode and (self._drag is not None or self._resize_dir):
            self.save_geometry()
        self._drag = None
        self._resize_dir = None
