"""Small manifest-driven FFmpeg editor with reusable shots, audio stems and safe audio-only remix."""
import argparse
from pathlib import Path
import sys
from media_common import (atomic_ffmpeg, binary, concat_path, digest, dimensions, duration,
                          file_hash, fit_filter, number, read_json, run, write_json)


def timestamp(seconds, ass=False):
    base = 100 if ass else 1000
    ticks = round(seconds * base)
    s, sub = divmod(ticks, base)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02}:{s:02}.{sub:02}" if ass else f"{h:02}:{m:02}:{s:02},{sub:03}"


def subtitles(project, out, total, w, h):
    settings = project.get("subtitle_style", {})
    font = settings.get("font", "sans-serif")
    if any(c in font for c in ",\r\n"):
        raise ValueError("Subtitle font must be a plain font-family name")
    size = number(settings.get("size", round(h * .046)), "font size", True)
    margin = number(settings.get("margin_v", round(h * .07)), "subtitle margin")
    text = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,{max(1,h*.003)},0,2,30,30,{margin},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    srt = []
    rows = sorted(project.get("subtitles", []), key=lambda s: s["start"])
    for i, row in enumerate(rows, 1):
        start, end = number(row["start"], "subtitle start"), number(row["end"], "subtitle end", True)
        if end <= start or end > total + .001:
            raise ValueError("Subtitle outside timeline or end <= start")
        plain = str(row["text"]).replace("\r", "")
        escaped = plain.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", "\\N")
        text += f"Dialogue: 0,{timestamp(start,True)},{timestamp(end,True)},Default,,0,0,0,,{escaped}\n"
        srt.append(f"{i}\n{timestamp(start)} --> {timestamp(end)}\n{plain}\n")
    (out / "subtitles.ass").write_text(text, encoding="utf-8-sig")
    (out / "subtitles.srt").write_text("\n".join(srt), encoding="utf-8")


def make_audio(track, source, target):
    slot = track["duration"]
    begin = number(track.get("in", 0), "audio in")
    available = duration(source) - begin
    if available <= 0:
        raise ValueError("Audio in point is after the end of its source")
    source_length = number(track.get("source_duration", available), "source_duration", True)
    if source_length > available + .03:
        raise ValueError("source_duration exceeds available audio")
    voice = track["role"] == "voice"
    loop = track.get("loop", False)
    if voice and loop:
        raise ValueError("Voice tracks cannot loop")
    if loop and "source_duration" in track:
        raise ValueError("Trim a loop region into its own source file; loop and source_duration cannot be combined")
    tempo = 1.0
    if voice:
        # Reserve a small tail so time-stretch rounding cannot clip the final phoneme.
        if slot <= .05:
            raise ValueError("Voice slot must be longer than 0.05 seconds")
        tempo = max(1.0, source_length / (slot - .05))
        limit = number(track.get("max_tempo", 1.2), "max_tempo", True)
        if not 1 <= limit <= 2 or tempo > limit + .00001:
            raise ValueError(f"Voice needs {tempo:.3f}x speed (limit {limit}); extend the slot or rewrite/re-synthesize")
    inputs = (["-stream_loop", "-1"] if loop else []) + ["-i", source]
    length = slot if loop else source_length
    filters = [f"atrim=start={begin}:duration={length}", "asetpts=PTS-STARTPTS"]
    if tempo > 1:
        filters.append(f"atempo={tempo:.9f}")
    if voice and track.get("normalize", True):
        filters.extend(["highpass=f=65", "loudnorm=I=-16:TP=-2:LRA=8"])
    gain = number(track.get("gain", 1), "gain")
    filters.extend(["aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo", f"volume={gain}"])
    filters.extend(["apad", f"atrim=duration={slot}"])
    for direction, key in [("in", "fade_in"), ("out", "fade_out")]:
        fade = number(track.get(key, 0), key)
        if fade > slot:
            raise ValueError(f"{key} is longer than its audio slot")
        if fade:
            filters.append(f"afade=t={direction}:st={0 if direction == 'in' else slot-fade}:d={fade}")
    atomic_ffmpeg([*inputs, "-vn", "-af", ",".join(filters), "-t", slot,
                   "-c:a", "pcm_f32le", "-ar", "48000", "-ac", "2"], target)
    return tempo


def mix(tracks, target, total, limiter=False):
    if not tracks:
        atomic_ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", total,
                       "-c:a", "pcm_s16le"], target)
        return
    inputs, filters, labels = [], [], []
    for i, (path, start) in enumerate(tracks):
        inputs.extend(["-i", path])
        filters.append(f"[{i}:a]adelay={round(start*48000)}S:all=1[a{i}]")
        labels.append(f"[a{i}]")
    tail = ",alimiter=limit=0.93:level=0:latency=1" if limiter else ""
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0{tail},apad,atrim=duration={total}[out]")
    atomic_ffmpeg([*inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-t", total,
                   "-c:a", "pcm_f32le", "-ar", "48000", "-ac", "2"], target)


def video_hash(path):
    return run([binary("ffmpeg"), "-v", "error", "-i", path, "-map", "0:v:0", "-c", "copy",
                "-f", "hash", "-hash", "sha256", "-"]).stdout.strip()


def build(project_file, out_dir, action="render", force=False):
    project_file, out = Path(project_file).resolve(), Path(out_dir).resolve()
    project = read_json(project_file)
    if project.get("version") != 1:
        raise ValueError("Expected project version 1")
    if not project.get("clips"):
        raise ValueError("At least one video/image clip is required")
    canvas = project.get("canvas", {})
    w, h, fps = dimensions(canvas.get("width", 1920), canvas.get("height", 1080), canvas.get("fps", 30))
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "cache"
    cache.mkdir(exist_ok=True)
    tool_version = run([binary("ffmpeg"), "-version"]).stdout.splitlines()[0]
    code_version = digest([file_hash(__file__), file_hash(Path(__file__).with_name("media_common.py"))])
    hashes = {}

    def source_info(row):
        path = (project_file.parent / row["source"]).resolve()
        if not path.is_file():
            raise ValueError(f"Missing source: {row['source']}")
        if path not in hashes:
            hashes[path] = file_hash(path)
        return path, hashes[path]

    shots, total = [], 0.0
    encode = ["-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p", "-threads", "2"]
    for row in project["clips"]:
        source, checksum = source_info(row)
        length = number(row["duration"], "clip duration", True)
        if abs(length * fps - round(length * fps)) > .001:
            raise ValueError(f"Clip duration {length} must be a multiple of 1/{fps} second")
        begin = number(row.get("in", 0), "clip in")
        kind = row.get("kind", "video")
        if kind not in ("video", "image"):
            raise ValueError("clip kind must be video or image")
        if kind == "video" and begin + length > duration(source) + .03:
            raise ValueError(f"Clip exceeds its source: {row['source']}")
        vf = f"{fit_filter(w,h,row.get('fit','contain'))},setsar=1,fps={fps}"
        key = digest([row, checksum, w, h, fps, tool_version, code_version])
        shots.append((source, cache / f"shot-{key}.mp4", length, begin, kind, vf, key))
        total += length

    audio = []
    for row in project.get("audio", []):
        row = dict(row)
        if row.get("role") not in ("voice", "music", "sfx"):
            raise ValueError("Audio role must be voice, music or sfx")
        row["start"] = number(row.get("start", 0), "audio start")
        row["duration"] = number(row["duration"], "audio duration", True)
        if row["start"] + row["duration"] > total + .001:
            raise ValueError("Audio slot extends beyond the video timeline")
        source, checksum = source_info(row)
        key = digest([row, checksum, tool_version, code_version])
        audio.append((row, source, cache / f"audio-{key}.wav"))

    visual_sig = digest([[s[-1] for s in shots], project.get("subtitles", []), project.get("subtitle_style", {})])
    report_path = out / "build.json"
    previous = read_json(report_path) if report_path.exists() else {}
    if action == "remix":
        if force or previous.get("visual_signature") != visual_sig or not (out / "final.mp4").exists():
            raise ValueError("Remix needs the unchanged visuals/subtitles from a successful render in this output directory")
        if video_hash(out / "final.mp4") != previous.get("video_sha256"):
            raise ValueError("Existing final.mp4 was modified; render again instead of remixing unknown video")
    subtitles(project, out, total, w, h)

    if action == "render":
        for source, target, length, begin, kind, vf, _ in shots:
            if force or not target.exists():
                inputs = ["-loop", "1", "-framerate", fps, "-i", source] if kind == "image" else ["-ss", begin, "-i", source]
                atomic_ffmpeg([*inputs, "-an", "-t", length, "-vf", vf, *encode], target)
        listing = out / "shots.ffconcat"
        listing.write_text("ffconcat version 1.0\n" + "".join(f"file {concat_path(s[1])}\n" for s in shots), encoding="utf-8")
        atomic_ffmpeg(["-safe", "0", "-f", "concat", "-i", listing, "-an", "-c:v", "copy",
                       "-movflags", "+faststart"], out / "picture.mp4")

    prepared, voice_info = [], []
    for row, source, target in audio:
        if force or not target.exists():
            tempo = make_audio(row, source, target)
        else:
            tempo = None
        prepared.append((target, row["start"], row["role"]))
        if row["role"] == "voice":
            voice_info.append({"source": row["source"], "slot": row["duration"], "tempo_if_rebuilt": tempo})
    # Floating-point stems preserve headroom until the final limiter.
    for role in ("voice", "music", "sfx"):
        mix([(p,s) for p,s,r in prepared if r == role], out / f"{role}.wav", total)
    mix([(out / f"{r}.wav", 0) for r in ("voice", "music", "sfx")], out / "mix.wav", total, limiter=True)

    mux = ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
           "-t", total, "-movflags", "+faststart"]
    atomic_ffmpeg(["-i", out / "picture.mp4", "-i", out / "mix.wav", *mux, "-c:v", "copy"], out / "clean.next.mp4")
    if action == "remix":
        atomic_ffmpeg(["-i", out / "final.mp4", "-i", out / "mix.wav", *mux, "-c:v", "copy"], out / "final.next.mp4")
    elif project.get("subtitles"):
        atomic_ffmpeg(["-i", out / "picture.mp4", "-i", out / "mix.wav", *mux,
                       "-vf", "ass=subtitles.ass", *encode], out / "final.next.mp4", cwd=out)
    else:
        atomic_ffmpeg(["-i", out / "picture.mp4", "-i", out / "mix.wav", *mux, "-c:v", "copy"], out / "final.next.mp4")
    (out / "clean.next.mp4").replace(out / "clean.mp4")
    (out / "final.next.mp4").replace(out / "final.mp4")
    actual = duration(out / "final.mp4")
    if abs(actual - total) > max(.1, 2/fps):
        raise RuntimeError(f"Unexpected final duration {actual:.3f}; expected {total:.3f}")
    report = {"action": action, "duration": total, "actual_duration": actual, "width": w, "height": h,
              "fps": fps, "visual_signature": visual_sig, "video_sha256": video_hash(out / "final.mp4"),
              "ffmpeg_version": tool_version, "voice_slots": voice_info,
              "manual_review_required": ["subtitle appearance", "speech endings", "mix listening", "transitions"]}
    write_json(report_path, report)
    write_json(out / "project.snapshot.json", project)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("render", "remix"))
    p.add_argument("--project", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--force", action="store_true", help="Rebuild cached render outputs (not valid for remix)")
    a = p.parse_args()
    result = build(a.project, a.out, a.action, a.force)
    print(f"{a.action}: {result['duration']:.2f}s, {result['width']}x{result['height']} @ {result['fps']}fps")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, KeyError, OSError) as e:
        sys.exit(str(e))
