import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.song_parser import parse_song, is_dfh_tab, parse_dfh_tab, note_token, clean_song_body, rhythm_to_beats, dfh_key_state
from src.constants import combo_state


class TestParseSong:
    def test_basic_notes(self):
        s = parse_song("TITLE=测试\n1 2 3 4 5 6 7 8\n")
        assert s.title == "测试"
        assert len(s.notes) == 8
        for i in range(8):
            assert s.notes[i] == (float(i), 1, i, 0)

    def test_extension_marks(self):
        s = parse_song("1 - -\n")
        assert len(s.notes) == 1
        assert s.notes[0] == (0.0, 3, 0, 0)

    def test_rest(self):
        s = parse_song("1 0 2\n")
        assert len(s.notes) == 2
        assert s.notes[0] == (0.0, 1, 0, 0)
        assert s.notes[1] == (2.0, 1, 1, 0)

    def test_prefix_b(self):
        s = parse_song("b5\n")
        assert s.notes[0] == (0.0, 1, 4, 1)

    def test_prefix_hash(self):
        s = parse_song("#2\n")
        assert s.notes[0] == (0.0, 1, 1, 2)

    def test_prefix_caret(self):
        s = parse_song("^1\n")
        assert s.notes[0] == (0.0, 1, 0, 3)

    def test_prefix_hash_b(self):
        s = parse_song("#b5\n")
        assert s.notes[0][3] == 4

    def test_prefix_b_hash(self):
        s = parse_song("b#5\n")
        assert s.notes[0][3] == 4

    def test_prefix_hash_caret(self):
        s = parse_song("#^1\n")
        assert s.notes[0][3] == 5

    def test_measure_line_ignored(self):
        s = parse_song("1 | 2 | 3\n")
        assert len(s.notes) == 3

    def test_total_beats(self):
        s = parse_song("1 - 2\n")
        assert s.total_beats == 3.0

    def test_i_as_eighth(self):
        s = parse_song("i\n")
        assert s.notes[0][2] == 7

    def test_no_title_uses_fallback(self):
        s = parse_song("1 2\n", fallback_title="无名")
        assert s.title == "无名"

    def test_bpm_parsed(self):
        s = parse_song("BPM=120\nTITLE=快歌\n1\n")
        assert s.bpm == 120.0

    def test_bpm_invalid_defaults_90(self):
        s = parse_song("BPM=abc\n1\n")
        assert s.bpm == 90.0


class TestComboState:
    def test_empty(self):
        assert combo_state("") == 0

    def test_b(self):
        assert combo_state("b") == 1

    def test_hash(self):
        assert combo_state("#") == 2

    def test_caret(self):
        assert combo_state("^") == 3

    def test_hash_b(self):
        assert combo_state("#b") == 4

    def test_b_hash(self):
        assert combo_state("b#") == 4

    def test_hash_caret(self):
        assert combo_state("#^") == 5

    def test_caret_hash(self):
        assert combo_state("^#") == 5

    def test_b_caret(self):
        assert combo_state("b^") == 3


class TestDfhTab:
    def test_is_dfh_tab_yes(self):
        text = "键位标记：+ 升调 / - 降调 / # 半音\n小节 1 (4/4)\n简谱 1\n键位 Z\n节奏 4"
        assert is_dfh_tab(text) is True

    def test_is_dfh_tab_no(self):
        assert is_dfh_tab("TITLE=测试\n1 2 3\n") is False

    def test_rhythm_table(self):
        assert rhythm_to_beats("1") == 4.0
        assert rhythm_to_beats("2") == 2.0
        assert rhythm_to_beats("4") == 1.0
        assert rhythm_to_beats("8") == 0.5
        assert rhythm_to_beats("16") == 0.25
        assert rhythm_to_beats("2·") == 3.0
        assert rhythm_to_beats("4·") == 1.5

    def test_rhythm_custom(self):
        assert rhythm_to_beats("2.5b") == 2.5

    def test_rhythm_unknown(self):
        assert rhythm_to_beats("xyz") == 1.0

    def test_dfh_key_state(self):
        assert dfh_key_state("") == 0
        assert dfh_key_state("-") == 1
        assert dfh_key_state("#") == 2
        assert dfh_key_state("+") == 3
        assert dfh_key_state("#-") == 4
        assert dfh_key_state("+#") == 5

    def test_parse_dfh_tab_basic(self):
        text = (
            "念张师 主旋律 — 三角洲口琴谱\n"
            "BPM 120\n"
            "键位标记：+ 升调 / - 降调 / # 半音\n\n"
            "小节 1 (4/4)\n"
            "  简谱  1   2\n"
            "  键位  Z   X\n"
            "  节奏  4   4\n"
        )
        s = parse_dfh_tab(text, fallback_title="fallback")
        assert len(s.notes) == 2
        assert s.notes[0] == (0.0, 1.0, 0, 0)
        assert s.notes[1] == (1.0, 1.0, 1, 0)
        assert s.bpm == 120.0


class TestNoteToken:
    def test_basic(self):
        assert note_token(0, 0) == "1"
        assert note_token(6, 0) == "7"
        assert note_token(7, 0) == "8"

    def test_prefix(self):
        assert note_token(0, 1) == "b1"
        assert note_token(0, 2) == "#1"
        assert note_token(0, 3) == "^1"
        assert note_token(0, 4) == "#b1"
        assert note_token(0, 5) == "#^1"


class TestCleanSongBody:
    def test_strips_headers(self):
        text = "BPM=90\nTITLE=测试\n1 2 3\n"
        body = clean_song_body(text)
        assert "BPM=" not in body
        assert "TITLE=" not in body
        assert "1 2 3" in body
