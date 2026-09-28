import os
import tempfile

import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

from src.midi_import import (
    _pitch_to_channel_state,
    import_midi,
    notes_to_song_text,
)


class TestPitchMapping:
    def test_natural_do(self):
        ch, st = _pitch_to_channel_state(60)
        assert ch == 0
        assert st == 0

    def test_natural_re(self):
        ch, st = _pitch_to_channel_state(62)
        assert ch == 1
        assert st == 0

    def test_natural_mi(self):
        ch, st = _pitch_to_channel_state(64)
        assert ch == 2
        assert st == 0

    def test_natural_fa(self):
        ch, st = _pitch_to_channel_state(65)
        assert ch == 3
        assert st == 0

    def test_natural_sol(self):
        ch, st = _pitch_to_channel_state(67)
        assert ch == 4
        assert st == 0

    def test_natural_la(self):
        ch, st = _pitch_to_channel_state(69)
        assert ch == 5
        assert st == 0

    def test_natural_si(self):
        ch, st = _pitch_to_channel_state(71)
        assert ch == 6
        assert st == 0

    def test_high_do(self):
        ch, st = _pitch_to_channel_state(72)
        assert ch == 7
        assert st == 0

    def test_c_sharp(self):
        ch, st = _pitch_to_channel_state(61)
        assert ch == 0
        assert st == 3

    def test_b_flat(self):
        ch, st = _pitch_to_channel_state(70)
        # Bb(70) 离 A(69) 差 +1，选 A 升半音
        assert ch == 5
        assert st == 3

    def test_octave_up(self):
        ch, st = _pitch_to_channel_state(84)
        assert ch == 0
        assert st == 0

    def test_octave_down(self):
        ch, st = _pitch_to_channel_state(48)
        assert ch == 0
        assert st == 0

    def test_extreme_high(self):
        ch, st = _pitch_to_channel_state(96)
        assert ch == 0
        assert st == 0

    def test_extreme_low(self):
        ch, st = _pitch_to_channel_state(36)
        assert ch == 0
        assert st == 0


def _make_midi(path, notes, bpm=120, title="Test Song"):
    """创建一个简单的 MIDI 文件用于测试。

    notes: [(pitch, start_tick, duration_tick), ...]
    """
    mid = MidiFile(ticks_per_beat=480)
    track = MidiTrack()
    mid.tracks.append(track)

    track.append(MetaMessage("track_name", name=title, time=0))
    tempo = int(60_000_000 / bpm)
    track.append(MetaMessage("set_tempo", tempo=tempo, time=0))

    events = []
    for pitch, start, dur in notes:
        events.append(("on", start, pitch))
        events.append(("off", start + dur, pitch))
    events.sort(key=lambda e: e[1])

    prev_tick = 0
    for kind, tick, pitch in events:
        delta = tick - prev_tick
        if kind == "on":
            track.append(Message("note_on", note=pitch, velocity=64, time=delta))
        else:
            track.append(Message("note_off", note=pitch, velocity=0, time=delta))
        prev_tick = tick

    mid.save(path)


class TestImportMidi:
    def test_basic_scale(self, tmp_path):
        path = str(tmp_path / "scale.mid")
        notes = [(60, 0, 480), (62, 480, 480), (64, 960, 480),
                 (65, 1440, 480), (67, 1920, 480)]
        _make_midi(path, notes, bpm=120, title="C Scale")

        title, bpm, parsed = import_midi(path)
        assert title == "C Scale"
        assert bpm == 120.0
        assert len(parsed) == 5
        assert parsed[0] == (0.0, 1.0, 0, 0)
        assert parsed[1] == (1.0, 1.0, 1, 0)
        assert parsed[2] == (2.0, 1.0, 2, 0)
        assert parsed[3] == (3.0, 1.0, 3, 0)
        assert parsed[4] == (4.0, 1.0, 4, 0)

    def test_sharps_and_flats(self, tmp_path):
        path = str(tmp_path / "accidentals.mid")
        notes = [(61, 0, 480), (70, 480, 480)]
        _make_midi(path, notes, bpm=90)

        title, bpm, parsed = import_midi(path)
        assert len(parsed) == 2
        assert parsed[0][2] == 0 and parsed[0][3] == 3
        # Bb(70) -> A 升半音 (ch=5, st=3)
        assert parsed[1][2] == 5 and parsed[1][3] == 3

    def test_high_do(self, tmp_path):
        path = str(tmp_path / "high.mid")
        notes = [(72, 0, 480)]
        _make_midi(path, notes, bpm=100)

        _, _, parsed = import_midi(path)
        assert parsed[0] == (0.0, 1.0, 7, 0)

    def test_octave_transposition(self, tmp_path):
        path = str(tmp_path / "octave.mid")
        notes = [(84, 0, 480)]
        _make_midi(path, notes, bpm=100)

        _, _, parsed = import_midi(path)
        assert parsed[0][2] == 0

    def test_empty_midi(self, tmp_path):
        path = str(tmp_path / "empty.mid")
        _make_midi(path, [], bpm=100)

        _, _, parsed = import_midi(path)
        assert parsed == []

    def test_rest_between_notes(self, tmp_path):
        path = str(tmp_path / "rest.mid")
        notes = [(60, 0, 240), (64, 960, 480)]
        _make_midi(path, notes, bpm=100)

        _, _, parsed = import_midi(path)
        assert len(parsed) == 2
        assert parsed[0][0] == 0.0
        assert parsed[1][0] == 2.0

    def test_default_bpm(self, tmp_path):
        path = str(tmp_path / "nobpm.mid")
        mid = MidiFile(ticks_per_beat=480)
        track = MidiTrack()
        mid.tracks.append(track)
        track.append(Message("note_on", note=60, velocity=64, time=0))
        track.append(Message("note_off", note=60, velocity=0, time=480))
        mid.save(path)

        _, bpm, _ = import_midi(path, default_bpm=90.0)
        assert bpm == 90.0


class TestNotesToText:
    def test_basic_output(self):
        notes = [(0.0, 1.0, 0, 0), (1.0, 1.0, 4, 0), (2.0, 1.0, 7, 0)]
        text = notes_to_song_text("Test", 90, notes)
        assert "TITLE=Test" in text
        assert "BPM=90" in text
        assert "1" in text
        assert "5" in text
        assert "8" in text

    def test_accidental_output(self):
        notes = [(0.0, 1.0, 0, 3)]
        text = notes_to_song_text("Sharp", 90, notes)
        assert "^1" in text

    def test_flat_output(self):
        notes = [(0.0, 1.0, 6, 1)]
        text = notes_to_song_text("Flat", 90, notes)
        assert "b7" in text

    def test_long_duration(self):
        notes = [(0.0, 4.0, 0, 0)]
        text = notes_to_song_text("Long", 90, notes)
        tokens = text.strip().split("\n")[-1].split()
        assert "1" in tokens
        assert tokens.count("-") >= 3

    def test_rest_output(self):
        notes = [(0.0, 1.0, 0, 0), (3.0, 1.0, 1, 0)]
        text = notes_to_song_text("Rest", 90, notes)
        assert "0" in text
