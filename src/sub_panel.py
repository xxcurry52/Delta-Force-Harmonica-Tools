from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget

from .config import hotkey_text
from .constants import THEME
from .winapi import GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TRANSPARENT, user32


class SubPanel(QWidget):
    HEIGHT = 92
    PAD = 10.0
    BTN_H = 26.0

    def __init__(self, overlay):
        super().__init__(None,
                         Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.ov = overlay
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(float(overlay.cfg.get("opacity", 0.94)))
        self.setMouseTracking(True)
        self.hover_action = None
        self._hit_buttons = []

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
            print("[sub] 设置窗口样式失败:", e)

    def sync_geometry(self):
        ov = self.ov
        pw = max(100, int(ov._panel_width()))
        x = ov.x()
        y = ov.y() + ov.height()
        try:
            scr = QApplication.primaryScreen().availableGeometry()
            if y + self.HEIGHT > scr.bottom():
                y = ov.y() - self.HEIGHT
            y = max(scr.top(), min(y, scr.bottom() - self.HEIGHT))
        except Exception:
            pass
        self.setGeometry(x, y, pw, self.HEIGHT)

    def _view(self):
        ov = self.ov
        if ov._sub_kind() == "rate":
            return {
                "kind": "rate",
                "title": "跟随倍速",
                "value": ov._follow_rate(),
                "lo": 0.2, "hi": 2.0,
                "actions": ("rate_down", "rate_up"),
                "hotkeys": ("rate_down", "rate_up"),
                "labels": ("− 减慢", "＋ 加快"),
                "words": ("减慢", "加快"),
                "accent": THEME["primary"],
            }
        return {
            "kind": "block",
            "title": "方块长度",
            "value": ov._leader_scale(),
            "lo": 0.5, "hi": 2.0,
            "actions": ("block_down", "block_up"),
            "hotkeys": ("rate_down", "rate_up"),
            "labels": ("− 缩短", "＋ 拉长"),
            "words": ("缩短", "拉长"),
            "accent": THEME["success"],
        }

    def _btn_rects(self):
        w = float(self.width())
        iw = max(40.0, w - 2 * self.PAD)
        gap = 6.0
        bw = (iw - gap) / 2.0
        a_dn, a_up = self._view()["actions"]
        return [(a_dn, QRectF(self.PAD, 40.0, bw, self.BTN_H)),
                (a_up, QRectF(self.PAD + bw + gap, 40.0, bw, self.BTN_H))]

    def _elide(self, p, text, width):
        fm = QFontMetrics(p.font())
        return fm.elidedText(text, Qt.ElideRight, int(max(8.0, width)))

    def _hint_text(self):
        v = self._view()
        return "%s %s · %s %s" % (hotkey_text(self.cfg, v["hotkeys"][0]), v["words"][0],
                                  hotkey_text(self.cfg, v["hotkeys"][1]), v["words"][1])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        iw = max(40.0, w - 2 * self.PAD)
        ov = self.ov

        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        path.addRoundedRect(QRectF(1.0, 0.0, w - 1.0, h - 1.0), 11, 11)
        path.addRect(QRectF(w - 12.0, 0.0, 12.0, h - 1.0))
        path.addRect(QRectF(1.0, 0.0, 12.0, 12.0))
        p.setClipPath(path)
        p.setPen(Qt.NoPen)
        bg = QColor(THEME["bg_deep"])
        bg.setAlpha(int(self.cfg.get("bg_alpha", 150)))
        p.setBrush(bg)
        p.drawRect(QRectF(0, 0, w, h))
        p.setClipping(False)
        p.setPen(QPen(THEME["border_light"], 1))
        p.drawLine(QPointF(self.PAD, 1.5), QPointF(w - self.PAD, 1.5))

        v = self._view()
        val, lo, hi = v["value"], v["lo"], v["hi"]
        accent = v["accent"]

        p.setPen(THEME["text_primary"])
        p.setFont(QFont("Microsoft YaHei UI", 10, QFont.DemiBold))
        p.drawText(QRectF(self.PAD, 9.0, iw * 0.55, 16.0),
                   Qt.AlignLeft | Qt.AlignVCenter, v["title"])
        p.setPen(accent)
        p.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        p.drawText(QRectF(self.PAD, 9.0, iw, 16.0),
                   Qt.AlignRight | Qt.AlignVCenter, "%d%%" % round(val * 100))

        track = QRectF(self.PAD, 29.0, iw, 6.0)
        p.setPen(Qt.NoPen)
        p.setBrush(THEME["bg_muted"])
        p.drawRoundedRect(track, 3, 3)
        k = max(0.0, min(1.0, (val - lo) / (hi - lo)))
        bar = QColor(accent)
        p.setBrush(bar)
        p.drawRoundedRect(QRectF(track.left(), track.top(),
                                 max(4.0, track.width() * k), track.height()), 3, 3)
        mid = track.left() + track.width() * ((1.0 - lo) / (hi - lo))
        p.setPen(QPen(THEME["border"], 1))
        p.drawLine(QPointF(mid, track.top() - 2.0), QPointF(mid, track.bottom() + 2.0))

        self._hit_buttons = []
        rects = self._btn_rects()
        for i, (action, r) in enumerate(rects):
            label = v["labels"][i]
            hover = (self.hover_action == action)
            bg = THEME["bg_hover"] if hover else THEME["bg_card"]
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, 6, 6)
            p.setPen(THEME["text_primary"])
            p.setFont(QFont("Microsoft YaHei UI", 9, QFont.DemiBold))
            p.drawText(r, Qt.AlignCenter, label)
            self._hit_buttons.append((r, action))

        hint = self._hint_text()
        p.setPen(THEME["text_muted"])
        p.setFont(QFont("Microsoft YaHei UI", 8))
        p.drawText(QRectF(self.PAD, 71.0, iw, 13.0), Qt.AlignLeft | Qt.AlignVCenter,
                   self._elide(p, hint, iw))

    def _button_at(self, pos):
        for r, action in self._hit_buttons:
            if r.contains(pos):
                return action
        return None

    def mousePressEvent(self, e):
        action = self._button_at(e.position())
        if not action:
            return
        d = 0.1 if action.endswith("_up") else -0.1
        if action.startswith("rate_"):
            self.ov.change_rate(d)
        else:
            self.ov.change_block_scale(d)
        self.update()

    def mouseMoveEvent(self, e):
        a = self._button_at(e.position())
        if a != self.hover_action:
            self.hover_action = a
            self.update()

    def leaveEvent(self, e):
        if self.hover_action:
            self.hover_action = None
            self.update()
