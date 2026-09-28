"""设置对话框 — 热键自定义、外观、演奏参数"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                                QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
                                QCheckBox, QComboBox, QTabWidget, QWidget,
                                QScrollArea, QFrame, QGroupBox, QLineEdit)

from .constants import KEY_DISPLAY, THEME


HOTKEY_LABELS = {
    "toggle_visible": "显示/隐藏窗口",
    "next_song": "下一首",
    "toggle_adjust": "调整窗口",
    "toggle_play": "从头重来",
    "toggle_panel": "面板穿透",
    "editor": "曲谱编辑器",
    "toggle_record": "开始/结束录音",
    "save_song": "保存曲谱",
    "toggle_mode": "切换模式",
    "rate_up": "倍速+ / 方块+",
    "rate_down": "倍速- / 方块-",
    "quit": "退出程序",
}


class KeyCaptureEdit(QLineEdit):
    """按下组合键自动填入"""

    def __init__(self, initial="", parent=None):
        super().__init__(initial, parent)
        self.setReadOnly(True)
        self.setPlaceholderText("点击后按键…")
        self._capturing = False

    def mousePressEvent(self, e):
        self._capturing = True
        self.setStyleSheet("border: 2px solid #007AFF; border-radius: 10px;")
        self.setText("按键…")

    def keyPressEvent(self, e):
        if not self._capturing:
            return super().keyPressEvent(e)
        import ctypes
        user32 = ctypes.windll.user32
        mods = []
        if user32.GetAsyncKeyState(0x10) & 0x8000:
            mods.append("shift")
        if user32.GetAsyncKeyState(0x11) & 0x8000:
            mods.append("ctrl")
        if user32.GetAsyncKeyState(0x12) & 0x8000:
            mods.append("alt")
        vk = e.nativeVirtualKey()
        if vk in (0x10, 0x11, 0x12):
            return
        from .winapi import vk_name
        name = vk_name(vk)
        if name and name not in ("Shift", "Ctrl", "Alt"):
            parts = mods + [name.lower()]
            self.setText("+".join(parts))
        self._capturing = False
        self.setStyleSheet("")


class SettingsDialog(QDialog):
    settings_changed = Signal(dict)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("设置")
        self.setMinimumSize(520, 460)
        self._apply_theme()
        self._build_ui()

    def _apply_theme(self):
        bg = "#F2F2F7"
        card = "#FFFFFF"
        text = "#1D1D1F"
        text2 = "#6E6E73"
        border = "#E5E5EA"
        primary = "#007AFF"
        primary_hover = "#0062CC"
        self.setStyleSheet(f"""
            QDialog {{ background: {bg}; }}
            QLabel {{ color: {text}; font-family: "Microsoft YaHei UI"; font-size: 13px; }}
            QTabWidget::pane {{ border: none; background: transparent; top: -1px; }}
            QTabBar::tab {{
                background: transparent; color: {text2};
                padding: 7px 20px; border-radius: 999px;
                font-family: "Microsoft YaHei UI"; font-size: 13px; font-weight: 600;
                margin: 3px;
            }}
            QTabBar::tab:hover {{ color: {text}; background: rgba(0,0,0,0.03); }}
            QTabBar::tab:selected {{ background: {card}; color: {text}; border: 1px solid {border}; }}
            QTabWidget::tab-bar {{ alignment: center; }}
            QPushButton {{
                background: {card}; color: {text}; border: 1px solid {border};
                border-radius: 17px; padding: 8px 18px;
                font-family: "Microsoft YaHei UI"; font-size: 13px; font-weight: 600;
                min-height: 34px;
            }}
            QPushButton:hover {{ background: #F2F2F7; }}
            QPushButton#primary {{ background: {primary}; color: #fff; border-color: {primary}; }}
            QPushButton#primary:hover {{ background: {primary_hover}; border-color: {primary_hover}; }}
            QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {{
                background: {card}; color: {text};
                border: 1px solid {border}; border-radius: 10px;
                padding: 6px 10px; font-family: "Microsoft YaHei UI"; font-size: 13px;
                min-height: 32px;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
                border: 2px solid {primary};
            }}
            QCheckBox {{ color: {text}; font-family: "Microsoft YaHei UI"; font-size: 13px; spacing: 8px; }}
            QCheckBox::indicator {{ width: 20px; height: 20px; border-radius: 6px; border: 1px solid {border}; background: {card}; }}
            QCheckBox::indicator:checked {{ background: {primary}; border: 2px solid {primary}; }}
            QGroupBox {{
                color: {text2}; border: 1px solid {border};
                border-radius: 16px; margin-top: 12px; padding-top: 18px;
                font-family: "Microsoft YaHei UI"; font-size: 13px; font-weight: 700;
                background: {card};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 14px; top: 2px; text-transform: uppercase; letter-spacing: 0.04em; }}
            QScrollArea {{ border: none; background: transparent; }}
            QFrame#divider {{ background: {border}; max-height: 1px; }}
        """)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ---- 热键页 ----
        hk_tab = QWidget()
        hk_layout = QVBoxLayout(hk_tab)
        hk_layout.setSpacing(6)
        self._hk_edits = {}
        for action, label in HOTKEY_LABELS.items():
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch()
            cur = self.cfg.get("hotkeys", {}).get(action, "")
            edit = KeyCaptureEdit(cur)
            edit.setMinimumWidth(160)
            row.addWidget(edit)
            self._hk_edits[action] = edit
            hk_layout.addLayout(row)
        hk_layout.addStretch()
        tabs.addTab(hk_tab, "热键")

        # ---- 外观页 ----
        appear_tab = QWidget()
        appear_layout = QFormLayout(appear_tab)
        appear_layout.setSpacing(8)

        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.3, 1.0)
        self.opacity_spin.setSingleStep(0.02)
        self.opacity_spin.setValue(float(self.cfg.get("opacity", 0.94)))
        appear_layout.addRow("窗口不透明度", self.opacity_spin)

        self.bg_alpha_spin = QSpinBox()
        self.bg_alpha_spin.setRange(50, 255)
        self.bg_alpha_spin.setValue(int(self.cfg.get("bg_alpha", 150)))
        appear_layout.addRow("背景透明度", self.bg_alpha_spin)

        self.hit_offset_spin = QSpinBox()
        self.hit_offset_spin.setRange(0, 60)
        self.hit_offset_spin.setValue(int(self.cfg.get("hit_line_offset", 10)))
        appear_layout.addRow("判定线偏移", self.hit_offset_spin)

        self.panel_width_spin = QSpinBox()
        self.panel_width_spin.setRange(100, 300)
        self.panel_width_spin.setValue(int(self.cfg.get("panel_width", 168)))
        appear_layout.addRow("面板宽度", self.panel_width_spin)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("经典模式（方块下落）", "classic")
        self.mode_combo.addItem("跟随模式（实时演奏）", "follow")
        cur_mode = self.cfg.get("mode", "classic")
        self.mode_combo.setCurrentIndex(0 if cur_mode == "classic" else 1)
        appear_layout.addRow("演奏模式", self.mode_combo)

        tabs.addTab(appear_tab, "外观")

        # ---- 演奏页 ----
        play_tab = QWidget()
        play_layout = QFormLayout(play_tab)
        play_layout.setSpacing(8)

        self.follow_speed_spin = QDoubleSpinBox()
        self.follow_speed_spin.setRange(50, 500)
        self.follow_speed_spin.setSingleStep(10)
        self.follow_speed_spin.setValue(float(self.cfg.get("follow_speed", 200)))
        play_layout.addRow("跟随速度（像素/拍）", self.follow_speed_spin)

        self.follow_lead_spin = QDoubleSpinBox()
        self.follow_lead_spin.setRange(0.5, 10)
        self.follow_lead_spin.setSingleStep(0.5)
        self.follow_lead_spin.setValue(float(self.cfg.get("follow_lead", 2.0)))
        play_layout.addRow("跟随提前量（拍）", self.follow_lead_spin)

        self.hold_min_spin = QDoubleSpinBox()
        self.hold_min_spin.setRange(0.05, 1.0)
        self.hold_min_spin.setSingleStep(0.05)
        self.hold_min_spin.setValue(float(self.cfg.get("hold_min_seconds", 0.15)))
        play_layout.addRow("最短按住（秒）", self.hold_min_spin)

        self.block_scale_spin = QDoubleSpinBox()
        self.block_scale_spin.setRange(0.5, 2.0)
        self.block_scale_spin.setSingleStep(0.1)
        self.block_scale_spin.setValue(float(self.cfg.get("leader_block_scale", 1.0)))
        play_layout.addRow("经典方块长度倍率", self.block_scale_spin)

        self.follow_rate_spin = QDoubleSpinBox()
        self.follow_rate_spin.setRange(0.2, 2.0)
        self.follow_rate_spin.setSingleStep(0.1)
        self.follow_rate_spin.setValue(float(self.cfg.get("follow_rate", 1.0)))
        play_layout.addRow("跟随倍速", self.follow_rate_spin)

        self.countdown_spin = QSpinBox()
        self.countdown_spin.setRange(0, 10)
        self.countdown_spin.setValue(int(self.cfg.get("countdown_seconds", 3)))
        play_layout.addRow("倒计时（秒）", self.countdown_spin)

        self.mod_change_chk = QCheckBox("切音高算新音")
        self.mod_change_chk.setChecked(bool(self.cfg.get("mod_change_note", True)))
        play_layout.addRow("", self.mod_change_chk)

        self.hold_until_release = QCheckBox("经典模式：按住才消")
        self.hold_until_release.setChecked(bool(self.cfg.get("leader_hold_until_release", True)))
        play_layout.addRow("", self.hold_until_release)

        self.kb_monitor = QCheckBox("启用键盘监听")
        self.kb_monitor.setChecked(bool(self.cfg.get("keyboard_monitor", True)))
        play_layout.addRow("", self.kb_monitor)

        tabs.addTab(play_tab, "演奏")

        # ---- 按钮栏 ----
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_bar.addWidget(cancel_btn)
        ok_btn = QPushButton("保存")
        ok_btn.setObjectName("primary")
        ok_btn.clicked.connect(self._on_save)
        btn_bar.addWidget(ok_btn)
        layout.addLayout(btn_bar)

    def _on_save(self):
        new_cfg = dict(self.cfg)
        # 热键
        hotkeys = dict(new_cfg.get("hotkeys", {}))
        for action, edit in self._hk_edits.items():
            val = edit.text().strip()
            if val:
                hotkeys[action] = val
        new_cfg["hotkeys"] = hotkeys
        # 外观
        new_cfg["opacity"] = round(self.opacity_spin.value(), 2)
        new_cfg["bg_alpha"] = int(self.bg_alpha_spin.value())
        new_cfg["hit_line_offset"] = int(self.hit_offset_spin.value())
        new_cfg["panel_width"] = int(self.panel_width_spin.value())
        new_cfg["mode"] = self.mode_combo.currentData()
        # 演奏
        new_cfg["follow_speed"] = round(self.follow_speed_spin.value(), 1)
        new_cfg["follow_lead"] = round(self.follow_lead_spin.value(), 1)
        new_cfg["hold_min_seconds"] = round(self.hold_min_spin.value(), 2)
        new_cfg["leader_block_scale"] = round(self.block_scale_spin.value(), 1)
        new_cfg["follow_rate"] = round(self.follow_rate_spin.value(), 1)
        new_cfg["countdown_seconds"] = int(self.countdown_spin.value())
        new_cfg["mod_change_note"] = self.mod_change_chk.isChecked()
        new_cfg["leader_hold_until_release"] = self.hold_until_release.isChecked()
        new_cfg["keyboard_monitor"] = self.kb_monitor.isChecked()
        self.settings_changed.emit(new_cfg)
        self.accept()
