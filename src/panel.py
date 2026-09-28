import time

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import (QColor, QPainter, QPen, QFont, QFontMetrics, QPainterPath)
from PySide6.QtWidgets import QWidget

from .constants import (KEY_DISPLAY, PANEL_ROWS, STATE_MODS, STATE_NAMES, STATE_SHORT,
                          STRIP_COLORS, CHIP_LAYOUT, THEME)
from .config import hotkey_text
from .winapi import GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TRANSPARENT, user32
from .utils import square_plate_corner


class PanelWindow(QWidget):
    def __init__(self, overlay):
        super().__init__(None,
                         Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.ov = overlay
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(float(overlay.cfg.get("opacity", 0.94)))
        self.setMouseTracking(True)
        self.hover_action = None
        self._hit_buttons = []
        self._hit_songs = []
        self._hit_scrollbar = None
        self._sb_drag = None
        self._scrollbar_hot = False
        self._list_rows = 6
        self.song_scroll = 0
        self._drag = None
        self._resize_dir = None
        self._drag_origin = None

    @property
    def cfg(self):
        return self.ov.cfg

    def apply_style(self):
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_NOACTIVATE
            if self.cfg.get("panel_interactive", True):
                style &= ~WS_EX_TRANSPARENT
            else:
                style |= WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as e:
            print("[panel] 设置窗口样式失败:", e)

    def ensure_visible(self):
        self._compute_layout()
        cap = max(1, self._list_rows)
        idx = self.ov.song_idx
        if idx < self.song_scroll:
            self.song_scroll = idx
        elif idx >= self.song_scroll + cap:
            self.song_scroll = idx - cap + 1
        self.song_scroll = max(0, min(self.song_scroll,
                                      max(0, len(self.ov.songs) - cap)))

    LIST_ROW_H = 22.0
    BTN_H_MAX = 25.0
    BTN_H_MIN = 16.0
    BTN_GAP = 3.0
    BTN_HEAD_H = 18.0
    BOTTOM_M = 10.0

    def _compute_layout(self):
        w, h = float(self.width()), float(self.height())
        pad = 10.0
        iw = max(40.0, w - 2 * pad)
        lay = {"pad": pad, "iw": iw, "w": w, "h": h}
        y = 12.0
        lay["title"] = QRectF(pad, y, iw, 16); y += 20
        lay["song"] = QRectF(pad, y, iw, 15); y += 17
        lay["info"] = QRectF(pad, y, iw, 13); y += 16
        lay["chips"] = QRectF(pad, y, iw, 38); y += 42
        lay["modhint"] = QRectF(pad, y, iw, 13); y += 16
        lay["input"] = QRectF(pad, y, iw, 13); y += 17
        lay["list_header"] = QRectF(pad, y, iw, 14)
        list_top = y + 16.0

        n_btn = len(PANEL_ROWS)

        def block(bh):
            return self.BTN_HEAD_H + n_btn * (bh + self.BTN_GAP) - self.BTN_GAP

        bh = self.BTN_H_MAX
        while bh > self.BTN_H_MIN and (
                (h - self.BOTTOM_M - block(bh)) - list_top < self.LIST_ROW_H
                or list_top + self.LIST_ROW_H + block(bh) > h - self.BOTTOM_M):
            bh -= 1.0
        bb = block(bh)
        list_h = (h - self.BOTTOM_M - bb) - list_top
        btn_head_y = max(list_top + self.LIST_ROW_H, h - self.BOTTOM_M - bb)
        list_h = min(list_h, btn_head_y - list_top - 4)
        rows = max(1, int(list_h // self.LIST_ROW_H))

        lay["list_top"] = list_top
        lay["list_rows"] = rows
        lay["list_h"] = list_h
        lay["list_clip"] = QRectF(0.0, list_top - 2.0, w, list_h + 4.0)
        lay["btn_h"] = bh
        lay["btn_header"] = QRectF(pad, btn_head_y, iw, 15)
        lay["btn_top"] = btn_head_y + self.BTN_HEAD_H
        self._list_rows = rows
        return lay

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lay = self._compute_layout()
        self._draw(p, lay)

    def _elide(self, p, text, width):
        fm = QFontMetrics(p.font())
        return fm.elidedText(text, Qt.ElideRight, int(max(8.0, width)))

    def _button_label(self, action):
        if action == "editor":
            return ("● 录音中" if self.ov.recording else "添加曲谱",
                    bool(self.ov.recording))
        if action == "toggle_adjust":
            return ("调整窗口", self.ov.adjust_mode)
        if action == "toggle_play":
            return ("从头重来", False)
        if action == "toggle_panel":
            if self.cfg.get("panel_interactive", True):
                return ("面板穿透", False)
            return ("已穿透", True)
        if action == "toggle_visible":
            return ("隐藏窗口", False)
        if action == "next_song":
            return ("下一首", False)
        if action == "toggle_mode":
            follow = (self.ov.mode == "follow")
            return ("经典模式" if follow else "跟随演奏", follow)
        if action == "quit":
            return ("退出程序", False)
        return (action, False)

    def _hotkey_hint(self, action):
        return hotkey_text(self.cfg, action, "/")

    def _draw(self, p, lay):
        pad, iw = lay["pad"], lay["iw"]
        w, h = lay["w"], lay["h"]
        ov = self.ov

        # 面板背景（浅色毛玻璃底）
        p.setPen(Qt.NoPen)
        p.setBrush(THEME["bg_panel"])
        p.drawRoundedRect(6.0, 6.0, w - 12.0, h - 12.0, 16.0, 16.0)

        # 右侧分隔线
        p.setPen(QPen(THEME["border_light"], 1))
        p.drawLine(QPointF(w - 1.5, 10), QPointF(w - 1.5, h - 10))

        # 标题
        p.setPen(THEME["text_primary"])
        p.setFont(QFont("Microsoft YaHei UI", 12, QFont.DemiBold))
        p.drawText(lay["title"], Qt.AlignLeft | Qt.AlignVCenter, "口琴曲谱")

        # 当前曲名
        p.setPen(THEME["text_primary"])
        p.setFont(QFont("Microsoft YaHei UI", 11, QFont.DemiBold))
        p.drawText(lay["song"], Qt.AlignLeft | Qt.AlignVCenter,
                   self._elide(p, ov.song.title, iw))
        # 剩余进度
        p.setPen(THEME["text_secondary"])
        p.setFont(QFont("Microsoft YaHei UI", 9))
        info = "剩余 %d / %d 音" % (max(0, len(ov.song.notes) - ov.cursor),
                                   len(ov.song.notes))
        p.drawText(lay["info"], Qt.AlignLeft | Qt.AlignVCenter, info)

        # 状态指示块
        chip = lay["chips"]
        st_now = ov.current_state()
        cols = 3
        cw = (iw - (cols - 1) * 3.0) / cols
        for pos in range(6):
            st = CHIP_LAYOUT[pos]
            row, col = pos // cols, pos % cols
            r = QRectF(chip.left() + col * (cw + 3.0),
                       chip.top() + row * (chip.height() / 2 + 1.0),
                       cw, chip.height() / 2 - 1.0)
            active = (st == st_now)
            col_c = QColor(STRIP_COLORS[st])
            if not active:
                col_c.setAlpha(60)
            p.setPen(Qt.NoPen)
            p.setBrush(col_c)
            p.drawRoundedRect(r, 6, 6)
            if active and st in (0, 4):
                text_c = QColor(0x0F, 0x17, 0x2A)
            else:
                text_c = QColor(0xFF, 0xFF, 0xFF)
            if not active:
                text_c.setAlpha(180)
            p.setPen(text_c)
            p.setFont(QFont("Microsoft YaHei UI", 8, QFont.DemiBold))
            p.drawText(r, Qt.AlignCenter, STATE_SHORT[st])

        # 修饰键提示
        p.setFont(QFont("Microsoft YaHei UI", 9))
        if st_now == 0:
            hint = "本音：不用按修饰键"
        else:
            parts = []
            for role in STATE_MODS[st_now]:
                mods = [KEY_DISPLAY.get(n, n)
                        for n in self.cfg["modifier_keys"].get(role, ["?"])]
                parts.append("%s+%s" % (role, "+".join(mods)))
            hint = " + ".join(parts) + "  →  %s" % STATE_NAMES[st_now]
        p.setPen(THEME["text_secondary"])
        p.drawText(lay["modhint"], Qt.AlignLeft | Qt.AlignVCenter,
                   self._elide(p, hint, iw))

        # 输入检测
        if not ov._input_ok:
            txt, col = "输入：已关闭（config）", THEME["error"]
        elif ov._last_detect and time.monotonic() - ov._last_detect[0] < 2.5:
            txt, col = "检测到：%s" % ov._last_detect[1], THEME["success"]
        else:
            txt, col = "输入检测：待命", THEME["text_muted"]
        p.setPen(col)
        p.setFont(QFont("Microsoft YaHei UI", 9))
        p.drawText(lay["input"], Qt.AlignLeft | Qt.AlignVCenter, txt)

        # 曲谱列表标题
        n_songs = len(ov.songs)
        cap = lay["list_rows"]
        need_sb = n_songs > cap
        sb_w = 7.0 if need_sb else 0.0
        p.setPen(THEME["text_secondary"])
        p.setFont(QFont("Microsoft YaHei UI", 9))
        p.drawText(lay["list_header"], Qt.AlignLeft | Qt.AlignVCenter,
                   "曲谱列表（%d）%s" % (n_songs, "　滚轮翻页" if need_sb else ""))
        self._hit_songs = []
        self.song_scroll = max(0, min(self.song_scroll, max(0, n_songs - cap)))

        # 曲谱列表
        p.save()
        p.setClipRect(lay["list_clip"])
        for k in range(cap):
            idx = self.song_scroll + k
            if idx >= n_songs:
                break
            r = QRectF(pad - 4.0, lay["list_top"] + k * self.LIST_ROW_H, iw + 8.0, 20.0)
            self._hit_songs.append((idx, r))
            cur = (idx == ov.song_idx)
            if cur:
                p.setPen(Qt.NoPen)
                p.setBrush(THEME["primary"])
                p.drawRoundedRect(r, 8, 8)
            p.setPen(QColor(0xFF, 0xFF, 0xFF) if cur else THEME["text_secondary"])
            p.setFont(QFont("Microsoft YaHei UI", 9,
                            QFont.DemiBold if cur else QFont.Normal))
            tw = r.width() - 14.0 - sb_w
            p.drawText(QRectF(r.left() + 9.0, r.top(), tw, r.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       self._elide(p, "%d. %s" % (idx + 1, ov.songs[idx].title), tw))
        p.restore()

        # 滚动条
        self._hit_scrollbar = None
        if need_sb:
            track = QRectF(w - pad - 5.0, lay["list_top"] + 1.0,
                           5.0, max(20.0, lay["list_h"] - 2.0))
            span = max(0, n_songs - cap)
            thumb_h = max(26.0, track.height() * cap / float(n_songs))
            t = (self.song_scroll / float(span)) if span else 0.0
            thumb = QRectF(track.left(), track.top() + (track.height() - thumb_h) * t,
                           track.width(), thumb_h)
            p.setPen(Qt.NoPen)
            p.setBrush(THEME["bg_muted"])
            p.drawRoundedRect(track, 3, 3)
            hot = bool(self._sb_drag) or self._scrollbar_hot
            p.setBrush(THEME["text_muted"] if hot else THEME["border"])
            p.drawRoundedRect(thumb, 3, 3)
            self._hit_scrollbar = {"track": track, "thumb": thumb}

        # 热键按钮区标题
        p.setPen(THEME["text_secondary"])
        p.setFont(QFont("Microsoft YaHei UI", 9))
        p.drawText(lay["btn_header"], Qt.AlignLeft | Qt.AlignVCenter, "热键")
        self._hit_buttons = []
        y = lay["btn_top"]
        for row in PANEL_ROWS:
            n = len(row)
            gap = 4.0 if n > 1 else 0.0
            bw = (iw - gap * (n - 1)) / n
            for j, (action, _label) in enumerate(row):
                r = QRectF(pad + j * (bw + gap), y, bw, lay["btn_h"])
                label, active = self._button_label(action)
                hover = (self.hover_action == action)
                if active:
                    bg = THEME["primary"]
                elif hover:
                    bg = THEME["bg_hover"]
                else:
                    bg = THEME["bg_card"]
                p.setPen(Qt.NoPen)
                p.setBrush(bg)
                p.drawRoundedRect(r, 10, 10)
                text_c = QColor(0xFF, 0xFF, 0xFF) if active else THEME["text_primary"]
                p.setPen(text_c)
                p.setFont(QFont("Microsoft YaHei UI", 9, QFont.DemiBold))
                hint = self._hotkey_hint(action)
                hint_w = 0.0
                if hint:
                    fm8 = QFontMetrics(QFont("Microsoft YaHei UI", 8))
                    hint_w = fm8.horizontalAdvance(hint) + 10.0
                    while "/" in hint and r.width() - 16.0 - hint_w < 42.0:
                        hint = hint.rsplit("/", 1)[0]
                        hint_w = fm8.horizontalAdvance(hint) + 10.0
                    if r.width() - 16.0 - hint_w < 42.0:
                        hint, hint_w = "", 0.0
                p.drawText(QRectF(r.left() + 8.0, r.top(),
                                  max(10.0, r.width() - 16.0 - hint_w), r.height()),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           self._elide(p, label, r.width() - 16.0 - hint_w))
                if hint:
                    hint_c = QColor(0xFF, 0xFF, 0xFF, 180) if active else THEME["text_muted"]
                    p.setPen(hint_c)
                    p.setFont(QFont("Microsoft YaHei UI", 8))
                    p.drawText(QRectF(r.left(), r.top(), r.width() - 8.0, r.height()),
                               Qt.AlignRight | Qt.AlignVCenter,
                               self._elide(p, hint, r.width() * 0.5))
                self._hit_buttons.append((r, action))
            y += lay["btn_h"] + self.BTN_GAP

    def _button_at(self, pos):
        for r, action in self._hit_buttons:
            if r.contains(pos):
                return action
        return None

    def _song_at(self, pos):
        for idx, r in self._hit_songs:
            if r.contains(pos):
                return idx
        return None

    def _scroll_to(self, value):
        cap = max(1, self._list_rows)
        self.song_scroll = max(0, min(int(value),
                                      max(0, len(self.ov.songs) - cap)))
        self.update()

    def _scrollbar_press(self, pos):
        sb = self._hit_scrollbar
        if not sb:
            return False
        track, thumb = sb["track"], sb["thumb"]
        grab = QRectF(track.left() - 3.0, track.top(), track.width() + 6.0,
                      track.height())
        if not grab.contains(pos):
            return False
        cap = max(1, self._list_rows)
        span = max(0, len(self.ov.songs) - cap)
        if thumb.contains(pos):
            self._sb_drag = (pos.y(), self.song_scroll)
        else:
            self._scroll_to(self.song_scroll + (-cap if pos.y() < thumb.top() else cap))
        self.update()
        return True

    def _scrollbar_drag(self, pos):
        if not self._sb_drag:
            return False
        sb = self._hit_scrollbar
        if not sb:
            return False
        track, thumb = sb["track"], sb["thumb"]
        travel = max(1.0, track.height() - thumb.height())
        cap = max(1, self._list_rows)
        span = max(0, len(self.ov.songs) - cap)
        dy = pos.y() - self._sb_drag[0]
        self._scroll_to(self._sb_drag[1] + dy * span / travel)
        return True

    def _edge_at(self, pos):
        m = 9
        w, h = self.width(), self.height()
        l, r = pos.x() <= m, pos.x() >= w - m
        t, b = pos.y() <= m, pos.y() >= h - m
        if l and t: return "lt"
        if l and b: return "lb"
        if l: return "l"
        if r and t: return "rt"
        if r and b: return "rb"
        if r: return "r"
        if t: return "t"
        if b: return "b"
        return None

    def mousePressEvent(self, e):
        pos = e.position()
        action = self._button_at(pos)
        if action:
            if action == "toggle_visible":
                self.ov._say("窗口已隐藏 · 按 %s 叫回来"
                             % hotkey_text(self.cfg, "toggle_visible", " 或 "))
                self.ov.update()
                QTimer.singleShot(800, self._delayed_hide)
            else:
                self.ov.do_action(action)
            return
        if not self.ov.adjust_mode:
            if self._scrollbar_press(pos):
                return
            idx = self._song_at(pos)
            if idx is not None and idx != self.ov.song_idx:
                self.ov.select_song(idx)
            return
        self._resize_dir = self._edge_at(pos)
        g = e.globalPosition().toPoint()
        self._drag = g
        if not self._resize_dir:
            self._drag_origin = self.ov.pos()

    def _delayed_hide(self):
        if self.ov.isVisible():
            self.ov.do_action("toggle_visible")

    def mouseMoveEvent(self, e):
        pos = e.position()
        g = e.globalPosition().toPoint()
        if self.ov.adjust_mode:
            if self._drag is None:
                edge = self._edge_at(pos)
                cursors = {"l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
                           "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
                           "lt": Qt.SizeFDiagCursor, "rb": Qt.SizeFDiagCursor,
                           "rt": Qt.SizeBDiagCursor, "lb": Qt.SizeBDiagCursor}
                self.setCursor(cursors.get(edge, Qt.ArrowCursor))
                return
            geo = self.ov.frameGeometry()
            nx, ny, nw, nh = geo.x(), geo.y(), geo.width(), geo.height()
            if self._resize_dir:
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
                    self.ov.setGeometry(nx, ny, nw, nh)
                    self._drag = g
            elif self._drag_origin is not None:
                delta = g - self._drag
                self.ov.move(self._drag_origin + delta)
            return
        if self._sb_drag is not None and self._scrollbar_drag(pos):
            return
        hot = bool(self._hit_scrollbar and QRectF(
            self._hit_scrollbar["track"].left() - 3.0,
            self._hit_scrollbar["track"].top(),
            self._hit_scrollbar["track"].width() + 6.0,
            self._hit_scrollbar["track"].height()).contains(pos))
        if hot != self._scrollbar_hot:
            self._scrollbar_hot = hot
            self.update()
        act = self._button_at(pos)
        if act != self.hover_action:
            self.hover_action = act
            self.setCursor(Qt.PointingHandCursor if act else Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, e):
        if self.ov.adjust_mode and (self._drag is not None or self._resize_dir):
            self.ov.save_geometry()
        self._drag = None
        self._resize_dir = None
        self._drag_origin = None
        self._sb_drag = None
        self.update()

    def wheelEvent(self, e):
        self._compute_layout()
        cap = max(1, self._list_rows)
        if len(self.ov.songs) <= cap:
            return
        delta = -1 if e.angleDelta().y() > 0 else 1
        self.song_scroll = max(0, min(self.song_scroll + delta,
                                      max(0, len(self.ov.songs) - cap)))
        self.update()
