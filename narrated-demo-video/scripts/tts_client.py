"""Segmented Mambo-compatible JSON-to-WAV client; endpoint/headers stay out of manifests."""
import argparse
import io
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from media_common import digest, file_hash, number, read_json, write_json


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Do not forward private text/authorization to a different endpoint implicitly.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def wav_info(data):
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            rate, frames, channels = w.getframerate(), w.getnframes(), w.getnchannels()
            expected = frames * channels * w.getsampwidth()
            actual = len(w.readframes(frames))
        if rate <= 0 or frames <= 0 or actual != expected:
            raise ValueError("Empty or truncated WAV")
        return {"duration": frames / rate, "sample_rate": rate, "channels": channels}
    except (wave.Error, EOFError) as e:
        raise ValueError("TTS response is not a readable PCM WAV") from e


def post_wav(endpoint, payload, headers=None, timeout=120, retries=2):
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Use an HTTP(S) endpoint; supply authentication through the header environment variable")
    opener = urllib.request.build_opener(NoRedirect())
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(retries + 1):
        req = urllib.request.Request(endpoint, body,
                                     {"Content-Type": "application/json", **(headers or {})}, method="POST")
        try:
            with opener.open(req, timeout=timeout) as response:
                data = response.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise ValueError("TTS response exceeds 64 MiB")
            wav_info(data)
            return data
        except urllib.error.HTTPError as e:
            status = e.code
            e.close()
            if status not in (408, 429, 500, 502, 503, 504) or attempt == retries:
                raise RuntimeError(f"TTS HTTP {status}; verify the configured service. No alternate endpoint attempted.") from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise RuntimeError("TTS network error/timeout after bounded retries") from None
        time.sleep(min(2 ** (attempt + 1), 8))
    raise RuntimeError("TTS retries exhausted")


def synthesize(spec_path, out_dir, endpoint, headers=None, timeout=120, retries=2):
    spec, out = read_json(spec_path), Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    previous = {r["id"]: r for r in read_json(manifest_path)} if manifest_path.exists() else {}
    rows, seen = [], set()
    for segment in spec["segments"]:
        sid = str(segment["id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", sid) or sid in seen:
            raise ValueError("Segment IDs must be unique and contain only letters, digits, _ or -")
        seen.add(sid)
        payload = {"text_lang": "zh", "speed_factor": 1.0, "max_sec": 15,
                   **spec.get("defaults", {}), **segment.get("params", {}), "text": segment["text"]}
        if not isinstance(payload["text"], str) or not payload["text"].strip():
            raise ValueError(f"Segment {sid} has no text")
        number(payload["max_sec"], "max_sec", positive=True)
        key = digest({"endpoint": endpoint, "headers": headers or {}, "payload": payload})
        target = out / f"{sid}.wav"
        old = previous.get(sid, {})
        cached = (target.exists() and old.get("request_hash") == key
                  and old.get("sha256") == file_hash(target))
        if cached:
            data = target.read_bytes()
        else:
            data = post_wav(endpoint, payload, headers, timeout, retries)
            temp = target.with_suffix(".partial.wav")
            temp.write_bytes(data)
            temp.replace(target)
        info = wav_info(data)
        row = {"id": sid, "file": target.name, "text": payload["text"], "request_hash": key,
               "sha256": file_hash(target), **info}
        if info["duration"] >= float(payload["max_sec"]) * 0.95:
            row["warning"] = "Near max_sec: listen for a truncated ending; split/re-synthesize if needed"
        rows.append(row)
        # Preserve other cached entries if a later request fails; endpoints/headers are never written.
        previous[sid] = row
        write_json(manifest_path, list(previous.values()))
        print(f"{sid}: {info['duration']:.2f}s ({'cached' if cached else 'generated'})")
    write_json(manifest_path, rows)
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--endpoint-env", default="MAMBO_TTS_URL")
    p.add_argument("--headers-env", default="TTS_HEADERS_JSON")
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--retries", type=int, choices=range(4), default=2)
    a = p.parse_args()
    endpoint = os.environ.get(a.endpoint_env)
    if not endpoint:
        raise ValueError(f"Set {a.endpoint_env} to the user-authorized TTS endpoint")
    headers = json.loads(os.environ.get(a.headers_env, "{}"))
    if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise ValueError("Header environment variable must contain a JSON object of strings")
    synthesize(a.input, a.out, endpoint, headers, number(a.timeout, "timeout", True), a.retries)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, KeyError, OSError) as e:
        sys.exit(str(e))
