#!/usr/bin/env python3
"""Local labeling server for an STT evaluation set (V8.3 plan step S0).

Serves tools/eval-label.html on 127.0.0.1 only. Labels are appended to
<set>/labels.jsonl (latest line per item wins), so a crash never loses
earlier work and every revision stays auditable.

  python3 tools/eval-label-server.py data/eval/ko-lecture-v1 [--port 8790]

Blind items are sent to the page without Whisper's text.
"""
import argparse
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

PAGE = Path(__file__).with_name("eval-label.html")
STATUSES = {"ok", "nonspeech", "unintelligible"}


class LabelStore:
    def __init__(self, set_dir: Path):
        self.set_dir = set_dir
        self.items = [
            json.loads(line)
            for line in (set_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.by_id = {it["id"]: it for it in self.items}
        self.labels_path = set_dir / "labels.jsonl"
        self.lock = threading.Lock()
        self.labels = {}
        if self.labels_path.is_file():
            for line in self.labels_path.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("id") in self.by_id:
                    self.labels[rec["id"]] = rec

    def public_item(self, it):
        label = self.labels.get(it["id"])
        return {
            "id": it["id"],
            "mode": it["mode"],
            "session_id": it["session_id"],
            "segment": it.get("segment"),
            "duration_sec": it.get("duration_sec"),
            # Blind references must not be anchored on Whisper's output.
            "whisper_text": it.get("whisper_text", "") if it["mode"] == "correct" else "",
            "label": label,
        }

    def save(self, body):
        item = self.by_id.get(str(body.get("id") or ""))
        if item is None:
            raise ValueError("unknown item id")
        status = str(body.get("status") or "ok")
        if status not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        text = str(body.get("text") or "").strip()
        if status == "ok" and not text:
            raise ValueError("empty transcript: mark the item nonspeech or unintelligible instead")
        rec = {
            "id": item["id"],
            "mode": item["mode"],
            "status": status,
            "text": text if status == "ok" else "",
            "noisy": bool(body.get("noisy")),
            "note": str(body.get("note") or "").strip(),
            "labeled_at": datetime.now().astimezone().isoformat(),
        }
        with self.lock:
            with self.labels_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
            self.labels[item["id"]] = rec
        return rec


def make_handler(store: LabelStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, body, ctype):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status, obj):
            self.send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                return self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if path == "/api/items":
                return self.send_json(200, {
                    "set": store.set_dir.name,
                    "items": [store.public_item(it) for it in store.items],
                })
            if path.startswith("/clip/"):
                item = store.by_id.get(unquote(path[len("/clip/"):]))
                if item is None:
                    return self.send_json(404, {"error": "unknown item"})
                return self.send(200, (store.set_dir / item["clip"]).read_bytes(), "audio/wav")
            return self.send_json(404, {"error": "not found"})

        def do_POST(self):
            if urlparse(self.path).path != "/api/label":
                return self.send_json(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                return self.send_json(200, {"ok": True, "label": store.save(body)})
            except (ValueError, json.JSONDecodeError) as exc:
                return self.send_json(400, {"error": str(exc)})

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("set_dir", type=Path)
    ap.add_argument("--port", type=int, default=8790)
    args = ap.parse_args()
    store = LabelStore(args.set_dir.resolve())
    done = len(store.labels)
    print(f"{store.set_dir.name}: {len(store.items)} items, {done} labeled -> http://127.0.0.1:{args.port}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store)).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
