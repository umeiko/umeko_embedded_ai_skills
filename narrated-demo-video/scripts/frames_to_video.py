"""Convert timestamped capture frames to silent CFR H.264 without inventing timing."""
import argparse
from pathlib import Path
import sys
from media_common import (atomic_ffmpeg, concat_path, dimensions, fit_filter,
                          number, read_json, write_json)


def convert(manifest, output, width=1920, height=1080, fps=30):
    manifest, output = Path(manifest).resolve(), Path(output).resolve()
    w, h, fps = dimensions(width, height, fps)
    frames = read_json(manifest)
    if not isinstance(frames, list) or not frames:
        raise ValueError("frames.json must contain a nonempty list")
    times = [number(row["time"], "frame timestamp") for row in frames]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Frame timestamps must be strictly increasing")
    files = [(manifest.parent / row["file"]).resolve() for row in frames]
    if not all(p.is_file() for p in files):
        raise ValueError("A frame image is missing")
    output.parent.mkdir(parents=True, exist_ok=True)
    listing = output.with_suffix(".ffconcat")
    lines = ["ffconcat version 1.0"]
    spans = [b - a for a, b in zip(times, times[1:])] + [1 / fps]
    for path, span in zip(files, spans):
        lines.extend([f"file {concat_path(path)}", "option framerate 1000", f"duration {span:.9f}"])
    lines.append(f"file {concat_path(files[-1])}")
    lines.append("option framerate 1000")
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    length = sum(spans)
    atomic_ffmpeg(["-safe", "0", "-f", "concat", "-i", listing, "-an", "-t", length,
                   "-vf", f"{fit_filter(w,h)},setsar=1,fps={fps}", "-c:v", "libx264",
                   "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart"], output)
    info = {"duration": length, "frames_captured": len(files), "output_fps": fps,
            "has_audio": False, "max_capture_gap": max(spans)}
    write_json(output.with_suffix(".capture.json"), info)
    return info


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--fps", type=int, default=30)
    a = p.parse_args()
    print(convert(a.frames, a.output, a.width, a.height, a.fps))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, KeyError, OSError) as e:
        sys.exit(str(e))
