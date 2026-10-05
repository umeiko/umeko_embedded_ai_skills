"""Synthetic end-to-end checks; no user game, external TTS, or downloaded assets."""
import argparse
import copy
import io
import math
import os
from pathlib import Path
import struct
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import wave
from media_common import duration, file_hash, write_json
from frames_to_video import convert
from render_video import build, video_hash
from tts_client import synthesize


def tone(seconds, frequency=440, rate=24000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        w.writeframes(b"".join(struct.pack("<h", round(4000*math.sin(2*math.pi*frequency*i/rate)))
                               for i in range(round(seconds*rate))))
    return buffer.getvalue()


def expect_failure(fn, contains):
    try:
        fn()
    except (ValueError, RuntimeError) as e:
        assert contains.lower() in str(e).lower(), str(e)
    else:
        raise AssertionError(f"Expected rejection containing {contains}")


def exercise(root):
    # Spaces, Unicode and apostrophes cover common Windows/concat escaping failures.
    raw = root / "capture 空格's"
    raw.mkdir()
    frames = []
    for i, t in enumerate((0, .2, .65, 1.1, 1.7)):
        name = f"{i:03}.ppm"
        (raw / name).write_bytes(b"P6\n64 36\n255\n" + bytes([30+i*40, 90, 140])*(64*36))
        frames.append({"file": name, "time": 1000+t})
    write_json(raw / "frames.json", frames)
    info = convert(raw / "frames.json", root / "capture.mp4", 320, 180, 30)
    assert abs(duration(root / "capture.mp4") - info["duration"]) < .08
    write_json(raw / "bad.json", frames[:2] + [frames[0]])
    expect_failure(lambda: convert(raw / "bad.json", root / "bad.mp4"), "increasing")

    (root / "voice.wav").write_bytes(tone(.8))
    (root / "music.wav").write_bytes(tone(.3, 220))
    project = {"version": 1, "canvas": {"width": 320, "height": 180, "fps": 30},
               "clips": [{"source": "capture.mp4", "duration": 1.5},
                         {"source": "capture 空格's/001.ppm", "kind": "image", "duration": .5}],
               "audio": [{"role": "voice", "source": "voice.wav", "start": .2, "duration": 1},
                         {"role": "music", "source": "music.wav", "duration": 2, "gain": .2,
                          "loop": True, "fade_out": .2}],
               "subtitle_style": {"font": "sans-serif", "size": 12, "margin_v": 12},
               "subtitles": [{"start": .2, "end": 1.2, "text": "Demo caption\nSecond line"}]}
    manifest = root / "project.json"
    write_json(manifest, project)
    out = root / "render"
    report = build(manifest, out)
    assert abs(report["actual_duration"] - 2) < .08
    old_video, old_mix = video_hash(out / "final.mp4"), file_hash(out / "mix.wav")
    shot_times = {p.name: p.stat().st_mtime_ns for p in (out / "cache").glob("shot-*.mp4")}
    project["audio"][1]["gain"] = .5
    write_json(manifest, project)
    build(manifest, out, "remix")
    assert old_video == video_hash(out / "final.mp4"), "Audio-only remix changed the encoded video"
    assert old_mix != file_hash(out / "mix.wav"), "Changing music gain did not alter the mix"
    assert shot_times == {p.name: p.stat().st_mtime_ns for p in (out / "cache").glob("shot-*.mp4")}
    changed = copy.deepcopy(project)
    changed["subtitles"][0]["text"] = "Changed"
    write_json(manifest, changed)
    expect_failure(lambda: build(manifest, out, "remix"), "unchanged visuals")
    changed = copy.deepcopy(project)
    changed["audio"][0]["duration"] = .2
    write_json(manifest, changed)
    expect_failure(lambda: build(manifest, out / "too-short"), "Voice needs")
    write_json(manifest, project)

    # Local test server exercises the actual HTTP/WAV client without external text transfer.
    class Handler(BaseHTTPRequestHandler):
        requests = 0

        def log_message(self, *args):
            pass

        def do_POST(self):
            Handler.requests += 1
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if self.path == "/missing":
                self.send_error(404)
                return
            data = b"not a wav" if self.path == "/invalid" else tone(.4)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    request = root / "tts.json"
    write_json(request, {"segments": [{"id": "01", "text": "Local fixture only"}]})
    try:
        synthesize(request, root / "tts", endpoint + "/tts")
        synthesize(request, root / "tts", endpoint + "/tts")
        assert Handler.requests == 1, "Unchanged TTS request missed its cache"
        write_json(request, {"segments": [{"id": "01", "text": "Changed local fixture"}]})
        synthesize(request, root / "tts", endpoint + "/tts")
        assert Handler.requests == 2, "Changed narration did not invalidate its cache"
        expect_failure(lambda: synthesize(request, root / "tts", endpoint + "/missing"), "HTTP 404")
        assert Handler.requests == 3, "HTTP 404 should never be retried automatically"
        expect_failure(lambda: synthesize(request, root / "tts", endpoint + "/invalid"), "WAV")
        text = (root / "tts" / "manifest.json").read_text(encoding="utf-8")
        assert endpoint not in text, "Endpoint leaked to TTS manifest"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print("PASS: timestamp capture, encoding/subtitles/stems, audio-only remix, voice overrun rejection, TTS cache/404/invalid WAV")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ffmpeg", help="Optional FFmpeg executable; otherwise FFMPEG_BIN/PATH")
    p.add_argument("--out", help="Keep fixtures in a NEW directory for inspection")
    a = p.parse_args()
    if a.ffmpeg:
        os.environ["FFMPEG_BIN"] = a.ffmpeg
    if a.out:
        root = Path(a.out).resolve()
        root.mkdir(parents=True, exist_ok=False)
        exercise(root)
    else:
        with tempfile.TemporaryDirectory(prefix="demo-video-smoke-") as directory:
            exercise(Path(directory))


if __name__ == "__main__":
    main()
