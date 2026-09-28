import os
import re

from .constants import (KEY_INDEX, PREFIX_CHARS, STATE_NAMES, STATE_TOKEN_PREFIX,
                          combo_state)
from .config import SONGS_DIR


class Song:
    def __init__(self, title, bpm, notes, raw=""):
        self.title = title
        self.bpm = bpm
        self.notes = notes
        self.total_beats = max((s + d for s, d, _, _ in notes), default=0)
        self.raw = raw


def parse_song(text, fallback_title="未命名"):
    meta = {"BPM": "90", "TITLE": fallback_title}
    notes = []
    t = 0.0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        head = line.split("=", 1)
        if len(head) == 2 and head[0].strip().upper() in ("BPM", "TITLE"):
            meta[head[0].strip().upper()] = head[1].strip()
            continue
        for tok in line.split():
            if tok == "|":
                continue
            if tok == "-":
                if notes:
                    s, d, ch, st = notes[-1]
                    notes[-1] = (s, d + 1, ch, st)
                t += 1
                continue
            pref = ""
            while tok and tok[0] in PREFIX_CHARS:
                pref += tok[0]
                tok = tok[1:]
            state = combo_state(pref)
            ext = 0
            while tok.endswith("-"):
                ext += 1
                tok = tok[:-1]
            if tok == "0":
                t += 1 + ext
                continue
            if tok in ("8", "i", "I"):
                ch = 7
            elif tok.isdigit() and 1 <= int(tok) <= 7:
                ch = int(tok) - 1
            else:
                print("[谱面] 无法识别的记号已跳过:", repr(tok))
                t += 1 + ext
                continue
            dur = 1 + ext
            notes.append((t, dur, ch, state))
            t += dur
    try:
        bpm = float(meta.get("BPM", 90))
    except ValueError:
        bpm = 90.0
    return Song(meta.get("TITLE", fallback_title), bpm, notes, text)


def is_dfh_tab(text):
    s = str(text)
    return "键位标记" in s or ("小节" in s and "键位" in s)


def rhythm_to_beats(tok):
    tok = str(tok).strip()
    if tok.endswith("b"):
        try:
            return float(tok[:-1])
        except ValueError:
            return 1.0
    table = {
        "1": 4.0, "2·": 3.0, "2": 2.0, "4·": 1.5, "4": 1.0,
        "8·": 0.75, "8": 0.5, "16·": 0.375, "16": 0.25, "32": 0.125,
    }
    return table.get(tok, 1.0)


def dfh_key_state(mods):
    s = set(str(mods))
    if "#" in s:
        if "-" in s:
            return 4
        if "+" in s:
            return 5
        return 2
    if "-" in s:
        return 1
    if "+" in s:
        return 3
    return 0


def dfh_key_token(tok):
    tok = str(tok).strip()
    if not tok:
        return 0, 0
    idx = KEY_INDEX.get(tok[0].lower(), None)
    if idx is None:
        return 0, 0
    return idx, dfh_key_state(tok[1:])


def parse_dfh_tab(text, fallback_title="未命名"):
    title = fallback_title
    bpm = 90.0
    notes = []
    cur_beat = 0.0
    measure_len = 0.0
    in_measure = False
    keys = []
    rhythms = []

    def flush_measure():
        nonlocal cur_beat, keys, rhythms, in_measure
        if keys:
            offset = 0.0
            for ktok, rtok in zip(keys, rhythms):
                ch, st = dfh_key_token(ktok)
                dur = rhythm_to_beats(rtok)
                notes.append((cur_beat + offset, dur, ch, st))
                offset += dur
        cur_beat += measure_len
        keys = []
        rhythms = []
        in_measure = False

    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        if "键位标记" in line:
            continue
        if "三角洲口琴谱" in line and not line.startswith("BPM"):
            title = line.split("—")[0].strip() or fallback_title
            continue
        m = re.match(r"^BPM\s+([\d.]+)", line)
        if m:
            bpm = float(m.group(1))
            continue
        m = re.match(r"^小节\s+\d+\s*\((\d+)/(\d+)\)(.*)$", line)
        if m:
            if in_measure:
                flush_measure()
            num, den = int(m.group(1)), int(m.group(2))
            measure_len = num * 4.0 / den
            rest = m.group(3)
            if "—" in rest:
                cur_beat += measure_len
                in_measure = False
            else:
                in_measure = True
            continue
        if not in_measure:
            continue
        if line.startswith("键位"):
            keys = line[2:].strip().split()
        elif line.startswith("节奏"):
            rhythms = line[2:].strip().split()

    if in_measure:
        flush_measure()
    return Song(title, bpm, notes, text)


def safe_filename(name):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(name)).strip(" .")
    return s or "未命名"


def note_token(ch, state):
    state = max(0, min(len(STATE_NAMES) - 1, int(state)))
    prefix = STATE_TOKEN_PREFIX[state]
    digit = str(int(ch) + 1) if 0 <= int(ch) < 7 else "8"
    return prefix + digit


def clean_song_body(text):
    out = []
    for line in str(text).splitlines():
        head = line.split("=", 1)
        if len(head) == 2 and head[0].strip().upper() in ("BPM", "TITLE"):
            continue
        out.append(line)
    return "\n".join(out).strip()


def game_song_text(title, body):
    return "BPM=90\nTITLE=%s\n%s\n" % (title, str(body).strip())


def load_songs():
    songs = []
    if os.path.isdir(SONGS_DIR):
        for name in sorted(os.listdir(SONGS_DIR)):
            if name.lower().endswith(".txt"):
                path = os.path.join(SONGS_DIR, name)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if is_dfh_tab(content):
                        songs.append(parse_dfh_tab(content, os.path.splitext(name)[0]))
                    else:
                        songs.append(parse_song(content, os.path.splitext(name)[0]))
                except Exception as e:
                    print("[曲谱] 读取失败:", path, e)
    if not songs:
        songs.append(parse_song("TITLE=内置示例\n1 1 5 5 6 6 5 -\n", "内置示例"))
    return songs
