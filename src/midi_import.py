"""MIDI 文件导入模块

把标准 MIDI 文件解析成曲谱格式（与 song_parser.parse_song 输出兼容）。

三角洲口琴 8 个键对应 C 大调 1-8（do re mi fa sol la si 高音do），
MIDI 音高 60-67（C4-D5）。通过鼠标修饰键实现升降半音：

  state 0 = 本音（无修饰）
  state 1 = 降调（鼠标左键，降半音）
  state 2 = 半音（鼠标中键）
  state 3 = 升调（鼠标右键，升半音）
  state 4 = 半音+降调
  state 5 = 半音+升调

音高映射逻辑：以 C 大调为基础音阶，把 MIDI 音高转换成 (channel, state)。
超出 8 键范围的音自动八度移位到最近的可演奏音。
"""
import os

try:
    import mido
except ImportError:
    mido = None


# C 大调基础音高：do=60, re=62, mi=64, fa=65, sol=67, la=69, si=71, 高音do=72
# 简谱 1-8 -> MIDI pitch
BASE_PITCHES = [60, 62, 64, 65, 67, 69, 71, 72]

# 12 半音 -> 自然音的偏移量（相对 C 大调）
# 0=C, 1=C#, 2=D, 3=D#, 4=E, 5=F, 6=F#, 7=G, 8=G#, 9=A, 10=A#, 11=B
# 对于不在自然音上的半音，用修饰键实现：
#   偏 1 半音 = 升调(state 3) 或 降调(state 1)，取决于选哪个基础音
#   偏 2 半音不在一个八度内可表达时用半音键(state 2) + 升/降

# 半音偏移 -> (state, 基础音偏移)
# 正偏移=升，负偏移=降
ACCIDENTAL_MAP = {
    0: (0, 0),   # 本音
    1: (3, 0),   # 升半音 -> 升调(右键) + 同一基础音
    -1: (1, 0),  # 降半音 -> 降调(左键) + 同一基础音
    2: (2, 0),   # 全音偏离 -> 半音(中键)
    -2: (2, 0),
}


def _pitch_to_channel_state(pitch):
    """把 MIDI 音高映射到 (channel 0-7, state 0-5)。

    先八度移位到 60-71 范围（C4-B4），72 保持不变（高音 do），
    再找最近的自然音，差值用修饰键补偿。
    """
    # 72 = 高音 do，直接返回 channel 7
    if pitch == 72:
        return 7, 0

    # 八度移位到 60-71 范围
    p = pitch
    while p > 71:
        p -= 12
    while p < 60:
        p += 12
    if p == 72:
        return 7, 0

    # 找最近的自然音（只在前 7 个里找，不含高音 do）
    # 距离相同时优先选正偏移（升调）：C# 选 C 升而非 D 降
    best_ch = 0
    best_diff = 999
    for ch, base in enumerate(BASE_PITCHES[:7]):
        diff = p - base
        if abs(diff) < abs(best_diff):
            best_diff = diff
            best_ch = ch
        elif abs(diff) == abs(best_diff) and diff > best_diff:
            best_diff = diff
            best_ch = ch

    if best_diff == 0:
        return best_ch, 0

    if abs(best_diff) == 1:
        return best_ch, (3 if best_diff > 0 else 1)

    # 差 2 以上用半音键
    return best_ch, 2


def _ticks_to_beats(ticks, ticks_per_beat):
    if ticks_per_beat <= 0:
        return 1.0
    return ticks / ticks_per_beat


def import_midi(path, default_bpm=90.0, track_idx=None):
    """解析 MIDI 文件，返回 (title, bpm, notes)。

    notes 格式与 song_parser 一致：[(start_beat, dur_beats, channel, state), ...]
    """
    if mido is None:
        raise RuntimeError("需要安装 mido 库：pip install mido")

    mid = mido.MidiFile(path)
    ticks_per_beat = mid.ticks_per_beat or 480

    # 提取 tempo 和 title
    bpm = default_bpm
    title = os.path.splitext(os.path.basename(path))[0]

    # 选择主旋律 track
    tracks = mid.tracks
    if not tracks:
        return title, bpm, []

    # 如果指定了 track 就用那个，否则自动选 note 最多的 track
    if track_idx is not None and track_idx < len(tracks):
        target_tracks = [tracks[track_idx]]
    else:
        # 选 note_on 最多的 track
        scored = []
        for i, tr in enumerate(tracks):
            note_count = sum(1 for msg in tr if msg.type == "note_on" and msg.velocity > 0)
            scored.append((note_count, i))
        scored.sort(reverse=True)
        if scored[0][0] == 0:
            return title, bpm, []
        target_tracks = [tracks[scored[0][1]]]

    # 解析 tempo
    for tr in tracks:
        for msg in tr:
            if msg.type == "set_tempo":
                try:
                    bpm = 60_000_000 / msg.tempo
                except (ZeroDivisionError, TypeError):
                    pass
            if msg.type == "track_name" and msg.name:
                title = msg.name

    # 收集音符事件
    notes_raw = []
    for tr in target_tracks:
        abs_tick = 0
        for msg in tr:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                beat = _ticks_to_beats(abs_tick, ticks_per_beat)
                ch, st = _pitch_to_channel_state(msg.note)
                notes_raw.append([beat, ch, st, msg.note])

    if not notes_raw:
        return title, bpm, []

    # 计算每个音的持续时长：到下一个 note_on 的时间差
    notes_out = []
    for i, (beat, ch, st, _pitch) in enumerate(notes_raw):
        if i + 1 < len(notes_raw):
            next_beat = notes_raw[i + 1][0]
        else:
            next_beat = beat + 1.0
        dur = max(0.25, next_beat - beat)
        notes_out.append((beat, dur, ch, st))

    notes_out.sort(key=lambda n: n[0])
    return title, bpm, notes_out


def notes_to_song_text(title, bpm, notes):
    """把解析出的 notes 转成自带曲谱格式的文本。"""
    from .song_parser import note_token

    lines = ["BPM=%d" % round(bpm), "TITLE=%s" % title]

    beat_pos = 0.0
    line_tokens = []

    for start, dur, ch, st in notes:
        # 填休止
        if start > beat_pos + 0.01:
            gap = start - beat_pos
            gap_beats = int(round(gap))
            if gap_beats > 0:
                line_tokens.append("0")
                beat_pos += gap_beats

        token = note_token(ch, st)
        line_tokens.append(token)
        dur_int = int(round(dur))
        for _ in range(max(0, dur_int - 1)):
            line_tokens.append("-")
        beat_pos = start + dur

    # 按 16 个 token 一行排列
    lines.append("")
    count = 0
    cur_line = []
    for tok in line_tokens:
        cur_line.append(tok)
        count += 1
        if count >= 16:
            lines.append(" ".join(cur_line))
            cur_line = []
            count = 0
    if cur_line:
        lines.append(" ".join(cur_line))

    return "\n".join(lines) + "\n"
