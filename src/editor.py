import os
import re

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QFont, QShortcut, QKeySequence, QTextCursor
from PySide6.QtWidgets import (QWidget, QLineEdit, QPlainTextEdit, QPushButton,
                               QLabel, QVBoxLayout, QHBoxLayout, QFileDialog,
                               QMessageBox)

from .constants import KEY_LABELS, REC_WRAP
from .config import (SONGS_DIR, is_default_songs_dir, apply_songs_dir,
                      hotkey_text)
from .song_parser import (parse_song, clean_song_body, game_song_text,
                           safe_filename)
from .winapi import vk_of, vk_name

NOTE_RE = re.compile(r"^[b#^]{0,2}(?:[1-8]|[iI])-*$")


class SongTextEdit(QPlainTextEdit):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Z and (e.modifiers() & Qt.ControlModifier):
            self.editor.undo_one()
            return
        super().keyPressEvent(e)


class SongEditor(QWidget):
    def __init__(self, overlay):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.ov = overlay
        self.recording = False
        self.setWindowTitle("添加 / 编辑曲谱 — 口琴曲谱")
        self.resize(600, 620)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("给这首曲谱起个名字（例如：小星星）")
        self.name_edit.setMaxLength(40)
        lay.addWidget(self.name_edit)

        self.focus_hint = QLabel("提示：窗口没拿到焦点时打不了字 —— 先点一下这个窗口（标题栏或输入框）再输入。")
        self.focus_hint.setWordWrap(True)
        self.focus_hint.setStyleSheet("color:#c60; font-weight:600;")
        self.focus_hint.hide()
        lay.addWidget(self.focus_hint)

        tip = QLabel(
            "音符写法：1 2 3 4 5 6 7 8 = 按键 z x c v b n m ,（8 是逗号键）　"
            "前缀 ^ = 高音（按住鼠标右键）　b = 低音（左键）　# = 半音（中键）\n"
            "录音：点下面的「开始录音」（或按 %s），然后在游戏里照着弹一遍即可，"
            "录错了就点「撤销一个音」。\n"
            "保存：点「保存到曲谱库」；游戏在前台时也可以直接按 %s 保存（不用切窗口）。\n"
            "曲谱文件夹：默认在程序旁边的 songs 里（换电脑/分享只需整个文件夹一起拷）。"
            "想放到别处就点「曲谱文件夹…」。"
            % (self.ov.hk("toggle_record"), self.ov.hk("save_song")))
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666;")
        lay.addWidget(tip)

        self.text = SongTextEdit(self)
        f = QFont("Consolas")
        f.setStyleHint(QFont.Monospace)
        f.setPointSize(12)
        self.text.setFont(f)
        self.text.setPlaceholderText("这里会显示音符…（也可以直接手动输入 / 粘贴）")
        self.text.setTabChangesFocus(True)
        self.text.textChanged.connect(self._refresh_status)
        lay.addWidget(self.text, 1)

        self.rec_btn = QPushButton("● 开始录音（%s）" % self.ov.hk("toggle_record"))
        self.undo_btn = QPushButton("撤销一个音（Ctrl+Z）")
        self.clear_btn = QPushButton("清空")
        self.load_btn = QPushButton("载入当前曲谱")
        self.import_btn = QPushButton("从文件导入…")
        self.midi_btn = QPushButton("导入 MIDI…")
        self.save_btn = QPushButton("保存到曲谱库（Ctrl+S / %s）" % self.ov.hk("save_song"))
        self.export_btn = QPushButton("导出为文件…")
        self.folder_btn = QPushButton("曲谱文件夹…")
        self.open_btn = QPushButton("打开文件夹")
        self.rec_btn.setStyleSheet("font-weight:600;")

        lay.addLayout(self._row(self.rec_btn, self.undo_btn, self.clear_btn))
        lay.addLayout(self._row(self.load_btn, self.import_btn, self.midi_btn))
        lay.addLayout(self._row(self.save_btn, self.export_btn))
        lay.addLayout(self._row(self.folder_btn, self.open_btn))

        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.rec_btn.clicked.connect(self.toggle_record)
        self.undo_btn.clicked.connect(self.undo_one)
        self.clear_btn.clicked.connect(self.clear_all)
        self.load_btn.clicked.connect(self.load_current)
        self.import_btn.clicked.connect(self.import_file)
        self.midi_btn.clicked.connect(self.import_midi)
        self.save_btn.clicked.connect(self.save_to_library)
        self.export_btn.clicked.connect(self.export_file)
        self.folder_btn.clicked.connect(self.choose_folder)
        self.open_btn.clicked.connect(self.open_folder)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_to_library)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.export_file)
        QShortcut(QKeySequence("Escape"), self, activated=self.hide)
        self._refresh_status()

    @staticmethod
    def _row(*widgets):
        h = QHBoxLayout()
        h.setSpacing(6)
        for w in widgets:
            h.addWidget(w)
        return h

    def note_tokens(self):
        out = []
        for line in clean_song_body(self.text.toPlainText()).splitlines():
            for t in line.split("//")[0].split():
                if NOTE_RE.match(t):
                    out.append(t)
        return out

    def recorded_tokens(self):
        return self.note_tokens()

    def _cursor_to_end(self):
        c = self.text.textCursor()
        c.movePosition(QTextCursor.End)
        self.text.setTextCursor(c)

    def _refresh_status(self, *_):
        n = len(self.note_tokens())
        name = self.name_edit.text().strip() or "（还没起名字）"
        self.status.setText("曲名：%s ｜ 共 %d 个音 ｜ 保存位置：%s"
                            % (name, n, SONGS_DIR))
        self.status.setStyleSheet("color:#2a7; font-weight:600;" if n
                                  else "color:#999;")

    def toggle_record(self):
        self.ov.do_action("toggle_record")

    def set_recording_ui(self, on):
        self.recording = bool(on)
        hk = self.ov.hk("toggle_record")
        self.rec_btn.setText(("■ 结束录音（%s）" if on else "● 开始录音（%s）") % hk)
        self.rec_btn.setStyleSheet(
            "font-weight:600; background:#e24b4b; color:white;" if on
            else "font-weight:600;")
        self.text.setReadOnly(on)
        for w in (self.name_edit, self.clear_btn, self.load_btn, self.import_btn,
                  self.midi_btn):
            w.setEnabled(not on)
        self._refresh_status()

    def rec_append(self, token):
        lines = self.text.toPlainText().split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            lines = [token]
        else:
            st = lines[-1].strip()
            head = st.split("=", 1)[0].strip().upper()
            cur = lines[-1].rstrip()
            if st.startswith("//") or head in ("TITLE", "BPM"):
                lines.append(token)
            elif len([t for t in cur.split() if t != "|"]) >= REC_WRAP:
                lines.append(token)
            else:
                lines[-1] = (cur + " " + token) if cur else token
        self.text.setPlainText("\n".join(lines) + "\n")
        self._cursor_to_end()
        self.text.ensureCursorVisible()

    def undo_one(self):
        before = len(self.note_tokens())
        lines = self.text.toPlainText().rstrip("\n").split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            self.status.setText("没有可撤销的内容")
            return
        cur = lines[-1].rstrip()
        toks = cur.split()
        if not toks:
            lines.pop()
        elif toks[-1].startswith("//"):
            lines.pop()
        else:
            toks.pop()
            lines[-1] = " ".join(toks)
            if not lines[-1].strip():
                lines.pop()
        self.text.setPlainText(("\n".join(lines) + "\n") if lines else "")
        self._cursor_to_end()
        self.text.ensureCursorVisible()
        gone = before - len(self.note_tokens())
        if gone > 0:
            self.ov.truncate_rec(self.ov.rec_count - gone)
        self.status.setText("已撤销一个音 ｜ 现在共 %d 个音" % len(self.note_tokens()))

    def clear_all(self):
        if self.note_tokens() and QMessageBox.question(
                self, "清空", "确定清空当前编辑的内容吗？（曲谱库里已保存的文件不受影响）"
        ) != QMessageBox.Yes:
            return
        self.text.setPlainText("")
        self.ov.truncate_rec(0)

    def load_current(self):
        raw = getattr(self.ov.song, "raw", "") or ""
        if not raw:
            return
        self.text.setPlainText(clean_song_body(raw) + "\n")
        self.name_edit.setText(self.ov.song.title)
        self.status.setText("已载入《%s》的 %d 个音，改完记得点「保存到曲谱库」"
                            % (self.ov.song.title, len(self.ov.song.notes)))

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入曲谱文件", SONGS_DIR, "曲谱文件 (*.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return
        title = os.path.splitext(os.path.basename(path))[0]
        for line in text.splitlines():
            if line.strip().upper().startswith("TITLE="):
                title = line.split("=", 1)[1].strip() or title
                break
        self.text.setPlainText(clean_song_body(text) + "\n")
        self.name_edit.setText(title)
        self.status.setText("已导入：%s" % path)

    def import_midi(self):
        try:
            from .midi_import import import_midi, notes_to_song_text
        except ImportError:
            QMessageBox.warning(self, "缺少依赖",
                                 "导入 MIDI 需要安装 mido 库：\npip install mido")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 MIDI 文件", SONGS_DIR,
            "MIDI 文件 (*.mid *.midi);;所有文件 (*.*)")
        if not path:
            return
        try:
            title, bpm, notes = import_midi(path)
        except Exception as e:
            QMessageBox.warning(self, "MIDI 导入失败", str(e))
            return
        if not notes:
            QMessageBox.information(self, "没有音符",
                                    "这个 MIDI 文件里没有找到可识别的音符。")
            return
        text = notes_to_song_text(title, bpm, notes)
        self.text.setPlainText(text)
        self.name_edit.setText(title)
        self.status.setText("已导入 MIDI：%s（%d 个音，BPM %d）"
                            % (path, len(notes), round(bpm)))
        self.status.setStyleSheet("color:#2a7; font-weight:600;")

    def export_file(self):
        body = clean_song_body(self.text.toPlainText())
        if not body:
            QMessageBox.information(self, "还没有内容", "先录音或输入一些音符吧。")
            return
        name = self.name_edit.text().strip() or "未命名曲谱"
        from .config import BASE_DIR
        default = os.path.join(BASE_DIR, safe_filename(name) + ".txt")
        path, _ = QFileDialog.getSaveFileName(self, "导出曲谱", default,
                                              "曲谱文件 (*.txt)")
        if not path:
            return
        if not path.lower().endswith(".txt"):
            path += ".txt"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(game_song_text(name, body))
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        self.status.setText("已导出到：%s" % path)

    def choose_folder(self):
        from .config import SAMPLE_SONGS
        cur = SONGS_DIR
        d = QFileDialog.getExistingDirectory(
            self, "选一个文件夹当曲谱库（放进这里的 .txt 会出现在面板列表里）", cur)
        if not d:
            return
        d = os.path.normpath(d)
        val = "" if is_default_songs_dir(d) else d
        self.ov.cfg["songs_dir"] = val
        self.ov._save_config({"songs_dir": val})
        new = apply_songs_dir(self.ov.cfg)
        if not is_default_songs_dir(new):
            have = [n for n in os.listdir(new) if n.lower().endswith(".txt")]
            if not have and QMessageBox.question(
                    self, "这个文件夹里还没有曲谱",
                    "要把程序自带的示例曲谱复制到\n%s\n里面吗？" % new) == QMessageBox.Yes:
                for name, text in SAMPLE_SONGS.items():
                    path = os.path.join(new, name)
                    if not os.path.exists(path):
                        with open(path, "w", encoding="utf-8") as f:
                            f.write(text)
        self.ov.reload_songs()
        self._refresh_status()
        tail = "（默认：跟着程序走）" if is_default_songs_dir(new) else "（自定义）"
        self.status.setText("曲谱文件夹已切换%s：%s ｜ 现在共 %d 首"
                            % (tail, new, len(self.ov.songs)))
        self.status.setStyleSheet("color:#2a7; font-weight:600;")
        self.ov._say("曲谱文件夹：%s" % (os.path.basename(new) or new))

    def open_folder(self):
        os.makedirs(SONGS_DIR, exist_ok=True)
        try:
            os.startfile(SONGS_DIR)
        except Exception as e:
            QMessageBox.information(self, "曲谱文件夹",
                                    "曲谱就放在这个文件夹里：\n%s\n(%s)" % (SONGS_DIR, e))

    def save_to_library(self):
        return self._save(interactive=True)

    def save_quick(self):
        if self.recording:
            self.ov.set_recording(False)
        return self._save(interactive=False)

    def _save(self, interactive):
        body = clean_song_body(self.text.toPlainText())
        name = self.name_edit.text().strip() or self._suggest_name()
        if not body:
            if interactive:
                QMessageBox.information(self, "还没有内容",
                                        "先录一遍音（%s），或在文本框里输入音符。" % self.ov.hk("toggle_record"))
            else:
                self.ov._say("还没录到音符，没法保存（先按 %s 录一遍）" % self.ov.hk("toggle_record"))
            return False
        if not self.name_edit.text().strip():
            self.name_edit.setText(name)
        song = parse_song(game_song_text(name, body), name)
        if not song.notes:
            if interactive:
                QMessageBox.warning(
                    self, "没有识别到音符",
                    "文本里没有找到合法音符。\n写法示例：1 2 3 ^4 ^5 6 7 8\n"
                    "（1~8 对应按键 z x c v b n m ,  ，^ 表示高音）")
            else:
                self.ov._say("文本里没有合法音符，没法保存")
            return False
        os.makedirs(SONGS_DIR, exist_ok=True)
        path = os.path.join(SONGS_DIR, safe_filename(name) + ".txt")
        if os.path.exists(path):
            if interactive:
                if QMessageBox.question(
                        self, "覆盖确认",
                        "曲谱库里已经有《%s》了，要覆盖它吗？" % name
                ) != QMessageBox.Yes:
                    return False
            else:
                i = 2
                while os.path.exists(os.path.join(
                        SONGS_DIR, safe_filename("%s%d" % (name, i)) + ".txt")):
                    i += 1
                name = "%s%d" % (name, i)
                self.name_edit.setText(name)
                path = os.path.join(SONGS_DIR, safe_filename(name) + ".txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(game_song_text(name, body))
        except Exception as e:
            if interactive:
                QMessageBox.warning(self, "保存失败", str(e))
            else:
                self.ov._say("保存失败：%s" % e)
            return False
        self.ov.reload_songs(select_title=name)
        self.status.setText("已保存：%s（%d 个音）→ %s  面板列表已刷新"
                            % (name, len(song.notes), path))
        self.status.setStyleSheet("color:#2a7; font-weight:600;")
        if not interactive:
            self.ov._say("已保存《%s》（%d 个音）｜按 %s 换曲试听"
                         % (name, len(song.notes), self.ov.hk("next_song")))
        return True

    def show_editor(self):
        self.show()
        self.raise_()
        self.activateWindow()
        if not self.name_edit.text().strip():
            self.name_edit.setText(self._suggest_name())
            self.name_edit.selectAll()
        self._refresh_status()
        QTimer.singleShot(200, self._update_focus_hint)

    def _suggest_name(self):
        exist = set()
        try:
            for n in os.listdir(SONGS_DIR):
                exist.add(os.path.splitext(n)[0])
        except Exception:
            pass
        for i in range(1, 999):
            name = "我的曲谱%d" % i if i > 1 else "我的曲谱"
            if name not in exist:
                return name
        return "我的曲谱"

    def _update_focus_hint(self):
        self.focus_hint.setVisible(not self.isActiveWindow())

    def changeEvent(self, e):
        if e.type() == QEvent.ActivationChange:
            self.focus_hint.setVisible(not self.isActiveWindow())
        super().changeEvent(e)

    def closeEvent(self, e):
        if self.recording:
            self.ov.set_recording(False)
        e.ignore()
        self.hide()
