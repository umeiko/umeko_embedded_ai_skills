"""Shared stdlib/FFmpeg helpers. No shell interpolation, credentials, or platform paths."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import wave


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def binary(name):
    value = os.environ.get(name.upper() + "_BIN") or shutil.which(name)
    if not value:
        raise ValueError(f"Missing {name}; set {name.upper()}_BIN or install it on PATH")
    return value


def run(args, cwd=None):
    result = subprocess.run([str(x) for x in args], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:])
    return result


def ffmpeg(args, cwd=None):
    return run([binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args], cwd)


def duration(path):
    """Prefer PCM WAV/ffprobe; allow FFmpeg's duration metadata when ffprobe is absent."""
    try:
        with wave.open(str(path), "rb") as f:
            return f.getnframes() / f.getframerate()
    except (wave.Error, EOFError):
        pass
    probe = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")
    if probe:
        data = json.loads(run([probe, "-v", "error", "-show_entries", "format=duration",
                               "-of", "json", path]).stdout)
        return number(data["format"]["duration"], "source duration", positive=True)
    result = subprocess.run([binary("ffmpeg"), "-hide_banner", "-i", str(path)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise ValueError(f"Cannot determine duration of {Path(path).name}; install ffprobe")
    h, m, s = map(float, match.groups())
    return h * 3600 + m * 60 + s


def number(value, name, positive=False):
    n = float(value)
    if not math.isfinite(n) or n < 0 or (positive and n == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return n


def concat_path(path):
    p = Path(path).resolve().as_posix()
    if "\n" in p or "\r" in p:
        raise ValueError("Newlines are not supported in media paths")
    return "'" + p.replace("'", "'\\''") + "'"


def dimensions(width, height, fps):
    w, h, f = int(width), int(height), int(fps)
    if w != float(width) or h != float(height) or f != float(fps) or w < 2 or h < 2 or w % 2 or h % 2 or not 1 <= f <= 120:
        raise ValueError("Width/height must be positive even integers; fps must be an integer in 1..120")
    return w, h, f


def fit_filter(w, h, fit="contain"):
    if fit == "contain":
        return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x101820"
    if fit == "cover":
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    raise ValueError("fit must be contain or cover")


def atomic_ffmpeg(args, output, cwd=None):
    out = Path(output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_name(out.stem + ".partial" + out.suffix)
    try:
        ffmpeg([*args, temp], cwd)
        temp.replace(out)
    finally:
        temp.unlink(missing_ok=True)
