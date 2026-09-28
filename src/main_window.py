"""主窗口模块 — 启动首屏

打开软件先显示这个窗口，包含曲库列表、播放控制、模式选择、
录音、编辑器、设置等全部功能。悬浮窗只负责显示。
"""
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetrics, QColor, QPalette
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QListWidget, QListWidgetItem, QPushButton,
                                QLabel, QComboBox, QCheckBox, QFrame, QSizePolicy,
                                QSlider, QGroupBox, QGridLayout)

from .constants import KEY_LABELS, THEME, STATE_SHORT, STRIP_COLORS


class MainWindow(QMainWindow):
    # Signals
    overlay_requested = Signal()
    quit_requested = Signal()
    next_song_requested = Signal()
    prev_song_requested = Signal()
    play_requested = Signal()
    pause_requested = Signal()
    song_selected = Signal()
    mode_changed = Signal(str)
    settings_requested = Signal()
    adjust_requested = Signal()
    panel_passthrough_requested = Signal()
    editor_requested = Signal()
    add_song_requested = Signal()
    record_requested = Signal()
    save_song_requested = Signal()
    rate_changed = Signal(float)
    block_scale_changed = Signal(float)
    opacity_changed = Signal(float)
    bg_alpha_changed = Signal(int)

    def __init__(self, cfg, songs, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.songs = songs
        self.song_idx = 0
        self._overlay_visible = False
        self._recording = False
        self.setWindowTitle("三角洲口琴工具")
        self.setMinimumSize(760, 580)
        self.resize(860, 640)
        self._apply_theme()
        self._build_ui()
        self._refresh_song_list()

    def _apply_theme(self):
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(0xEF, 0xF6, 0xFF))
        pal.setColor(QPalette.WindowText, QColor(0x1E, 0x3A, 0x8A))
        pal.setColor(QPalette.Base, QColor(0xFF, 0xFF, 0xFF))
        pal.setColor(QPalette.AlternateBase, QColor(0xE9, 0xEF, 0xF5))
        pal.setColor(QPalette.Text, QColor(0x1E, 0x3A, 0x8A))
        pal.setColor(QPalette.Button, QColor(0xFF, 0xFF, 0xFF))
        pal.setColor(QPalette.ButtonText, QColor(0x1E, 0x3A, 0x8A))
        pal.setColor(QPalette.Highlight, QColor(0x1E, 0x40, 0xAF))
        pal.setColor(QPalette.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
        self.setPalette(pal)
        self.setStyleSheet(self._stylesheet())

    def resizeEvent(self, e):
        super().resizeEvent(e)

    def _stylesheet(self, base=15, small=14, title=24):
        bg = "#F2F2F7"
        card = "#FFFFFF"
        muted = "#F2F2F7"
        hover = "#E5E5EA"
        text = "#1D1D1F"
        text2 = "#6E6E73"
        border = "#E5E5EA"
        primary = "#007AFF"
        primary_hover = "#0062CC"
        accent = "#34C759"
        danger = "#FF3B30"
        focus_ring = "#007AFF"
        return f"""
            QMainWindow {{ background: {bg}; }}
            QLabel {{ color: {text}; font-family: "Microsoft YaHei UI"; font-size: {small}px; }}
            QLabel#titleLabel {{ font-size: {title}px; font-weight: 700; color: {text}; letter-spacing: -0.02em; }}
            QLabel#sectionLabel {{ font-size: {base}px; font-weight: 700; color: {text2}; letter-spacing: 0.06em; }}
            QLabel#hintLabel {{ color: {text2}; font-size: {small}px; }}
            QLabel#statusLabel {{ color: {text2}; font-size: {small}px; }}
            QListWidget {{
                background: {card}; border: 1px solid {border};
                border-radius: 14px; padding: 10px;
                font-family: "Microsoft YaHei UI"; font-size: {base}px;
                color: {text}; outline: none;
            }}
            QListWidget::item {{ padding: 11px 14px; border-radius: 10px; min-height: 34px; }}
            QListWidget::item:hover {{ background: {hover}; }}
            QListWidget::item:selected {{ background: {primary}; color: #fff; }}
            QPushButton {{
                background: {card}; color: {text}; border: 1px solid {border};
                border-radius: 19px; padding: 10px 20px;
                font-family: "Microsoft YaHei UI"; font-size: {base}px; font-weight: 600;
                min-height: 38px;
            }}
            QPushButton:hover {{ background: {hover}; border-color: {border}; }}
            QPushButton:focus {{ border: 2px solid {focus_ring}; outline: none; }}
            QPushButton:pressed {{ background: {muted}; color: {text}; }}
            QPushButton#primary {{
                background: {primary}; color: #fff; border: 1px solid {primary};
            }}
            QPushButton#primary:hover {{ background: {primary_hover}; border-color: {primary_hover}; }}
            QPushButton#primary:focus {{ border: 2px solid {focus_ring}; }}
            QPushButton#primary:pressed {{ background: #0051A8; }}
            QPushButton#danger {{
                background: {danger}; color: #fff; border: 1px solid {danger};
            }}
            QPushButton#danger:hover {{ background: #E02E24; border-color: #E02E24; }}
            QPushButton#danger:focus {{ border: 2px solid {focus_ring}; }}
            QPushButton#danger:pressed {{ background: #C7211A; }}
            QPushButton:checked {{
                background: {primary}; color: #fff; border-color: {primary};
            }}
            QPushButton:checked:hover {{ background: {primary_hover}; }}
            QComboBox {{
                background: {card}; color: {text}; border: 1px solid {border};
                border-radius: 12px; padding: 10px 14px;
                font-family: "Microsoft YaHei UI"; font-size: {base}px;
                min-height: 38px;
            }}
            QComboBox:focus {{ border: 2px solid {focus_ring}; }}
            QComboBox::drop-down {{ border: none; width: 28px; }}
            QComboBox QAbstractItemView {{
                background: {card}; color: {text};
                selection-background-color: {primary};
                selection-color: #fff;
                border: 1px solid {border}; border-radius: 12px;
                padding: 6px;
            }}
            QCheckBox {{ color: {text2}; font-family: "Microsoft YaHei UI"; font-size: {small}px; spacing: 8px; }}
            QCheckBox::indicator {{ width: 22px; height: 22px; border-radius: 7px; border: 1px solid {border}; background: {card}; }}
            QCheckBox::indicator:checked {{ background: {primary}; border: 2px solid {primary}; }}
            QSlider::groove:horizontal {{
                background: {muted}; height: 6px; border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {primary}; width: 20px; height: 20px;
                margin: -7px 0; border-radius: 10px;
                border: 3px solid {card};
            }}
            QSlider::handle:horizontal:focus {{ border: 3px solid {focus_ring}; }}
            QSlider::sub-page:horizontal {{
                background: {primary}; border-radius: 3px;
            }}
            QGroupBox {{
                color: {text2}; border: 1px solid {border};
                border-radius: 18px; margin-top: 12px; padding-top: 26px;
                font-family: "Microsoft YaHei UI"; font-size: {base}px; font-weight: 700;
                background: {card};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; top: 6px;
                text-transform: uppercase; letter-spacing: 0.06em;
            }}
            QFrame#divider {{ background: {border}; max-height: 1px; }}
        """

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(16)

        # ---- 标题栏 ----
        top = QHBoxLayout()
        title = QLabel("三角洲口琴工具")
        title.setObjectName("titleLabel")
        top.addWidget(title)
        top.addStretch()
        keys_label = QLabel("按键：%s" % " ".join(KEY_LABELS))
        keys_label.setObjectName("hintLabel")
        top.addWidget(keys_label)
        root.addLayout(top)

        # ---- 分隔线 ----
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.HLine)
        root.addWidget(divider)

        # ---- 中部：左曲库 + 右控制 ----
        mid = QHBoxLayout()
        mid.setSpacing(18)

        # 左：曲库列表
        left_box = QVBoxLayout()
        left_box.setSpacing(10)
        lib_label = QLabel("曲库")
        lib_label.setObjectName("sectionLabel")
        left_box.addWidget(lib_label)
        self.song_title_label = QLabel("")
        self.song_title_label.setObjectName("hintLabel")
        left_box.addWidget(self.song_title_label)
        self.song_list = QListWidget()
        self.song_list.setMinimumHeight(200)
        self.song_list.itemClicked.connect(self._on_song_clicked)
        self.song_list.itemDoubleClicked.connect(self._on_song_double_click)
        left_box.addWidget(self.song_list)

        # 曲库按钮
        song_btns = QHBoxLayout()
        song_btns.setSpacing(10)
        self.prev_btn = QPushButton("上一首")
        self.prev_btn.clicked.connect(self._prev_song)
        song_btns.addWidget(self.prev_btn)
        self.next_btn = QPushButton("下一首")
        self.next_btn.clicked.connect(self._next_song)
        song_btns.addWidget(self.next_btn)
        left_box.addLayout(song_btns)
        mid.addLayout(left_box, 1)

        # 右：控制区（固定最小宽度，避免窗口缩放时挤压）
        right_container = QWidget()
        right_container.setMinimumWidth(340)
        right_container.setMaximumWidth(400)
        right_col = QVBoxLayout(right_container)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(14)

        # -- 演奏控制组 --
        play_group = QGroupBox("演奏")
        play_layout = QGridLayout(play_group)
        play_layout.setSpacing(10)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("经典模式", "classic")
        self.mode_combo.addItem("跟随模式", "follow")
        self.mode_combo.setMinimumWidth(130)
        cur_mode = self.cfg.get("mode", "classic")
        self.mode_combo.setCurrentIndex(0 if cur_mode == "classic" else 1)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_label = QLabel("模式")
        mode_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        play_layout.addWidget(mode_label, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        play_layout.addWidget(self.mode_combo, 0, 1)
        play_layout.setColumnStretch(0, 0)
        play_layout.setColumnStretch(1, 1)

        self.play_btn = QPushButton("开始演奏")
        self.play_btn.setObjectName("primary")
        self.play_btn.setMinimumHeight(42)
        self.play_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.play_btn.clicked.connect(self._on_play)
        play_layout.addWidget(self.play_btn, 1, 0, 1, 2)

        self.replay_btn = QPushButton("从头重来")
        self.replay_btn.setMinimumHeight(36)
        self.replay_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.replay_btn.clicked.connect(self._on_replay)
        play_layout.addWidget(self.replay_btn, 2, 0)

        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setMinimumHeight(36)
        self.pause_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.pause_btn.clicked.connect(self._on_pause)
        play_layout.addWidget(self.pause_btn, 2, 1)

        right_col.addWidget(play_group)

        # -- 速度/方块长度组 --
        speed_group = QGroupBox("速度 / 长度")
        speed_layout = QVBoxLayout(speed_group)
        speed_layout.setSpacing(12)

        def _slider_row(label_text, slider, value_label):
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            lbl.setMinimumWidth(36)
            row.addWidget(lbl)
            slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            row.addWidget(slider, 1)
            value_label.setMinimumWidth(44)
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            row.addWidget(value_label)
            return row

        # 倍速
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(20, 200)
        self.rate_slider.setValue(int(float(self.cfg.get("follow_rate", 1.0)) * 100))
        self.rate_slider.valueChanged.connect(self._on_rate_changed)
        self.rate_label = QLabel("100%")
        speed_layout.addLayout(_slider_row("倍速", self.rate_slider, self.rate_label))

        # 方块长度
        self.block_slider = QSlider(Qt.Horizontal)
        self.block_slider.setRange(50, 200)
        self.block_slider.setValue(int(float(self.cfg.get("leader_block_scale", 1.0)) * 100))
        self.block_slider.valueChanged.connect(self._on_block_changed)
        self.block_label = QLabel("100%")
        speed_layout.addLayout(_slider_row("方块", self.block_slider, self.block_label))

        # 透明度
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(float(self.cfg.get("opacity", 0.94)) * 100))
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.opacity_label = QLabel("94%")
        speed_layout.addLayout(_slider_row("透明", self.opacity_slider, self.opacity_label))

        # 背景透明度
        self.bg_slider = QSlider(Qt.Horizontal)
        self.bg_slider.setRange(100, 255)
        self.bg_slider.setValue(int(self.cfg.get("bg_alpha", 235)))
        self.bg_slider.valueChanged.connect(self._on_bg_alpha_changed)
        self.bg_label = QLabel("235")
        speed_layout.addLayout(_slider_row("背景", self.bg_slider, self.bg_label))

        right_col.addWidget(speed_group)

        # -- 工具组 --
        tool_group = QGroupBox("工具")
        tool_layout = QGridLayout(tool_group)
        tool_layout.setSpacing(10)
        tool_layout.setColumnMinimumWidth(0, 100)
        tool_layout.setColumnMinimumWidth(1, 100)

        def _tool_btn(text, slot=None, checkable=False):
            btn = QPushButton(text)
            btn.setCheckable(checkable)
            btn.setMinimumHeight(38)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if slot:
                btn.clicked.connect(slot)
            return btn

        self.record_btn = _tool_btn("录音", self._on_record, True)
        tool_layout.addWidget(self.record_btn, 0, 0)

        self.add_song_btn = _tool_btn("添加曲谱", self._on_add_song)
        tool_layout.addWidget(self.add_song_btn, 0, 1)

        self.editor_btn = _tool_btn("曲谱编辑器", self._on_editor)
        tool_layout.addWidget(self.editor_btn, 1, 0)

        self.save_btn = _tool_btn("保存曲谱", self._on_save_song)
        tool_layout.addWidget(self.save_btn, 1, 1)

        self.adjust_btn = _tool_btn("调整悬浮窗", self._on_adjust)
        tool_layout.addWidget(self.adjust_btn, 2, 0)

        self.passthrough_btn = _tool_btn("面板穿透", self._on_passthrough, True)
        tool_layout.addWidget(self.passthrough_btn, 2, 1)

        self.settings_btn = _tool_btn("设置", self._on_settings)
        tool_layout.addWidget(self.settings_btn, 3, 0, 1, 2)

        right_col.addWidget(tool_group)
        right_col.addStretch()
        mid.addWidget(right_container, 0)
        root.addLayout(mid, 1)

        # ---- 底部按钮栏 ----
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(12)

        self.overlay_btn = QPushButton("显示悬浮窗")
        self.overlay_btn.setObjectName("primary")
        self.overlay_btn.setMinimumWidth(120)
        self.overlay_btn.clicked.connect(self._toggle_overlay)
        btn_bar.addWidget(self.overlay_btn)

        btn_bar.addStretch()

        self.quit_btn = QPushButton("退出")
        self.quit_btn.setObjectName("danger")
        self.quit_btn.setMinimumWidth(80)
        self.quit_btn.clicked.connect(self._on_quit)
        btn_bar.addWidget(self.quit_btn)
        root.addLayout(btn_bar)

        # ---- 状态栏 ----
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("statusLabel")
        root.addWidget(self.status_label)

    def _refresh_song_list(self):
        self.song_list.clear()
        for i, s in enumerate(self.songs):
            item = QListWidgetItem("%d. %s  (%d 音)" % (i + 1, s.title, len(s.notes)))
            self.song_list.addItem(item)
        if self.songs:
            self.song_list.setCurrentRow(0)
            self.song_idx = 0
            self.song_title_label.setText(self.songs[0].title)

    def _on_song_clicked(self, item):
        row = self.song_list.row(item)
        if row >= 0 and row < len(self.songs):
            self.song_idx = row
            self.song_title_label.setText(self.songs[row].title)
            self.song_selected.emit()

    def _on_song_double_click(self, item):
        row = self.song_list.row(item)
        if row >= 0 and row < len(self.songs):
            self.song_idx = row
            self.song_title_label.setText(self.songs[row].title)
            self.play_requested.emit()
            self.status_label.setText("演奏中…")

    def _on_mode_changed(self, idx):
        mode = self.mode_combo.itemData(idx)
        self.cfg["mode"] = mode
        self.mode_changed.emit(mode)

    def _prev_song(self):
        if not self.songs:
            return
        self.song_idx = (self.song_idx - 1) % len(self.songs)
        self.song_list.setCurrentRow(self.song_idx)
        self.song_title_label.setText(self.songs[self.song_idx].title)
        self.prev_song_requested.emit()
        self.song_selected.emit()

    def _next_song(self):
        if not self.songs:
            return
        self.song_idx = (self.song_idx + 1) % len(self.songs)
        self.song_list.setCurrentRow(self.song_idx)
        self.song_title_label.setText(self.songs[self.song_idx].title)
        self.next_song_requested.emit()
        self.song_selected.emit()

    def _on_play(self):
        if self.song_list.currentRow() >= 0:
            self.song_idx = self.song_list.currentRow()
        self.play_requested.emit()
        self.status_label.setText("演奏中…")

    def _on_replay(self):
        self.play_requested.emit()
        self.status_label.setText("从头重来")

    def _on_pause(self):
        self.pause_requested.emit()
        if self.pause_btn.text() == "暂停":
            self.pause_btn.setText("继续")
            self.status_label.setText("已暂停")
        else:
            self.pause_btn.setText("暂停")
            self.status_label.setText("演奏中…")

    def _on_rate_changed(self, val):
        rate = val / 100.0
        self.rate_label.setText("%d%%" % val)
        self.rate_changed.emit(rate)

    def _on_block_changed(self, val):
        scale = val / 100.0
        self.block_label.setText("%d%%" % val)
        self.block_scale_changed.emit(scale)

    def _on_opacity_changed(self, val):
        opacity = val / 100.0
        self.opacity_label.setText("%d%%" % val)
        self.opacity_changed.emit(opacity)

    def _on_bg_alpha_changed(self, val):
        self.bg_label.setText(str(val))
        self.bg_alpha_changed.emit(val)

    def _on_add_song(self):
        self.add_song_requested.emit()

    def _on_record(self):
        self._recording = not self._recording
        self.record_btn.setChecked(self._recording)
        if self._recording:
            self.record_btn.setText("停止录音")
            self.record_btn.setStyleSheet("background: #EF4444; color: #fff;")
            self.status_label.setText("录音中…")
        else:
            self.record_btn.setText("录音")
            self.record_btn.setStyleSheet("")
            self.status_label.setText("录音结束")
        self.record_requested.emit()

    def _on_editor(self):
        self.editor_requested.emit()

    def _on_save_song(self):
        self.save_song_requested.emit()
        self.status_label.setText("曲谱已保存")

    def _on_adjust(self):
        self.adjust_requested.emit()
        self.status_label.setText("调整模式：拖动悬浮窗移动/缩放")

    def _on_passthrough(self):
        self.panel_passthrough_requested.emit()
        if self.passthrough_btn.isChecked():
            self.status_label.setText("面板穿透：开（鼠标可穿透）")
        else:
            self.status_label.setText("面板穿透：关（鼠标可交互）")

    def _toggle_overlay(self):
        self._overlay_visible = not self._overlay_visible
        if self._overlay_visible:
            self.overlay_btn.setText("隐藏悬浮窗")
            self.status_label.setText("悬浮窗已显示")
        else:
            self.overlay_btn.setText("显示悬浮窗")
            self.status_label.setText("悬浮窗已隐藏")
        self.overlay_requested.emit()

    def _on_settings(self):
        self.settings_requested.emit()

    def _on_quit(self):
        self.quit_requested.emit()
        self.close()

    def select_song(self, idx):
        if 0 <= idx < len(self.songs):
            self.song_idx = idx
            self.song_list.setCurrentRow(idx)
            self.song_title_label.setText(self.songs[idx].title)
