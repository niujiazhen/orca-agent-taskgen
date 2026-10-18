"""Local photo ingestion and token-scoped LAN capture. No model is called here."""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import secrets
import socket
import threading
import time
from urllib.parse import parse_qs, urlparse
import warnings

from orca_sim.taskgen.contracts import ContractError

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "HEIC"}


def normalize_image(raw: bytes, destination: str | Path) -> dict:
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    if not raw or len(raw) > MAX_BYTES:
        raise ContractError("Image must be non-empty and at most 20 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as im:
                if im.format not in SUPPORTED_FORMATS:
                    raise ContractError("Supported image formats: JPEG, PNG, WebP, HEIC/HEIF")
                if im.width * im.height > MAX_PIXELS:
                    raise ContractError("Decoded image exceeds 40 megapixels")
                if getattr(im, "n_frames", 1) != 1:
                    raise ContractError("Use a single still image, not an animation")
                image = ImageOps.exif_transpose(im).convert("RGB")
                # Re-encode without location EXIF or original metadata.
                image.info.clear()
                stream = BytesIO()
                image.save(stream, format="PNG")
                encoded = stream.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ContractError(f"Cannot decode image; convert HEIC to JPEG or install the photo extra: {exc}") from exc
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)
    return {"image": path.name, "sha256": hashlib.sha256(encoded).hexdigest(),
            "width": image.width, "height": image.height}


PAGE = """<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ORCA photo capture</title><style>
body{font:18px system-ui;max-width:650px;margin:36px auto;padding:20px;background:#f3f5f7;color:#182837}
button,label{display:block;background:#176b67;color:white;border:0;border-radius:9px;padding:15px;margin:15px 0;cursor:pointer}
input[type=file]{max-width:100%}img{max-width:100%;border-radius:9px}small{color:#536575}</style>
<h1>ORCA photo → scene</h1><p>Photograph the tabletop and its objects. Keep the whole object visible.</p>
<label>Take a photo <input id="camera" type="file" accept="image/*,.heic,.heif" capture="environment"></label>
<label>Choose a photo <input id="gallery" type="file" accept="image/*,.heic,.heif"></label>
<small>JPEG, PNG, WebP, HEIC/HEIF · up to 20 MB / 40 MP. Same Wi-Fi as the computer.</small>
<p id="status">Waiting for a photo</p><img id="photo" hidden><p id="results"></p>
<script>
const token=new URLSearchParams(location.search).get('token');
const auth='?token='+encodeURIComponent(token);const status=document.querySelector('#status');
async function upload(e){let file=e.target.files[0];if(!file)return;
 if(file.size>20*1024*1024){status.textContent='Photo exceeds 20 MB';return;}
 status.textContent='Uploading…';try{let r=await fetch('/upload'+auth,{method:'POST',body:file});let v=await r.json();
 if(!r.ok)throw Error(v.error);status.textContent='Uploaded. Return to Codex and say: Continue with the uploaded photo. / 继续处理刚上传的照片';
 document.querySelector('#photo').src='/artifacts/source.png'+auth+'&t='+Date.now();document.querySelector('#photo').hidden=false;
 }catch(e){status.textContent=e.message;}}
document.querySelector('#camera').onchange=upload;document.querySelector('#gallery').onchange=upload;
setInterval(async()=>{try{let r=await fetch('/status'+auth);let v=await r.json();
 if(v.state==='processing')status.textContent='Codex is generating the scene…';
 if(v.state==='failed')status.textContent='A check failed. Return to Codex for the details.';
 if(v.state==='ready'){status.textContent='Scene ready. Review it in Codex.';let box=document.querySelector('#results');box.replaceChildren();
 for(let item of v.artifacts){let a=document.createElement('a');a.href='/artifacts/'+encodeURIComponent(item)+auth;a.textContent=item;a.style.display='block';box.appendChild(a);}}
 }catch(e){}},2000);
</script></html>"""


class CaptureSession:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(24)
        self.lock = threading.Lock()
        self.created = time.time()
        self.state = "waiting"
        self.artifacts = {}
        self.receipt = None

    def status(self):
        return {"state": self.state, "receipt": self.receipt, "artifacts": sorted(self.artifacts)}

    def handler(self):
        session = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # Do not leak the session token into access logs.

            def reply(self, status, payload, content_type="application/json"):
                raw = json.dumps(payload).encode() if content_type == "application/json" else payload
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)

            def authorized(self):
                token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
                return secrets.compare_digest(token, session.token) and time.time()-session.created < 3600

            def do_GET(self):
                if not self.authorized():
                    return self.reply(403, {"error": "Invalid or expired capture session"})
                path = urlparse(self.path).path
                if path == "/":
                    return self.reply(200, PAGE.encode(), "text/html; charset=utf-8")
                if path == "/status":
                    # Codex may update only a small state/artifact manifest.
                    progress = session.directory/"progress.json"
                    if progress.is_file():
                        try:
                            value = json.loads(progress.read_text(encoding="utf-8"))
                            if value.get("state") in {"processing", "ready", "failed"}:
                                session.state = value["state"]
                            for name in value.get("artifacts", []):
                                if name in {"scene_preview.png", "scene_preview.mp4", "task_preview.png", "task_preview.mp4", "annotated.png"}:
                                    p = session.directory/name
                                    if p.is_file() and p.resolve().parent == session.directory:
                                        session.artifacts[name] = p
                        except (ValueError, OSError):
                            pass
                    return self.reply(200, session.status())
                if path.startswith("/artifacts/"):
                    name = path[len("/artifacts/"):]
                    p = session.artifacts.get(name)
                    if p and p.resolve().parent == session.directory:
                        kind = "video/mp4" if p.suffix == ".mp4" else "image/png"
                        return self.reply(200, p.read_bytes(), kind)
                return self.reply(404, {"error": "Not found"})

            def do_POST(self):
                if not self.authorized():
                    return self.reply(403, {"error": "Invalid or expired capture session"})
                if urlparse(self.path).path != "/upload":
                    return self.reply(404, {"error": "Not found"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size <= 0 or size > MAX_BYTES:
                        return self.reply(413, {"error": "Upload must be at most 20 MB"})
                    self.connection.settimeout(30)
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        raise ContractError("Incomplete upload")
                    with session.lock:
                        if session.receipt is not None:
                            return self.reply(409, {"error": "Session already has a photo; start a new capture for a new photo"})
                        receipt = normalize_image(raw, session.directory/"source.png")
                        session.receipt = receipt
                        session.state = "uploaded"
                        session.artifacts["source.png"] = session.directory/"source.png"
                        (session.directory/"receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
                    return self.reply(200, receipt)
                except (ValueError, OSError) as exc:
                    return self.reply(400, {"error": str(exc)})
        return Handler


def serve_capture(*, output="photo_captures", lan=False, port=8765, advertise_host=None, duration=3600):
    import qrcode
    directory = Path(output).resolve()/secrets.token_hex(6)
    session = CaptureSession(directory)
    server = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", port), session.handler())
    host = "127.0.0.1"
    if lan:
        if advertise_host:
            host = advertise_host
        else:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                    probe.connect(("8.8.8.8", 80))
                    host = probe.getsockname()[0]
            except OSError:
                server.server_close()
                raise ContractError("Cannot determine LAN address; pass --advertise-host <computer LAN IP>")
    url = f"http://{host}:{server.server_address[1]}/?token={session.token}"
    qrcode.make(url).save(directory/"qr.png")
    descriptor = {"url": url, "directory": str(directory), "qr": str(directory/"qr.png"),
                  "status": "waiting", "expires_in_seconds": duration}
    (directory/"capture-session.json").write_text(json.dumps(descriptor, indent=2), encoding="utf-8")
    print(json.dumps(descriptor, ensure_ascii=False), flush=True)
    server.timeout = .5
    deadline = time.monotonic()+duration
    try:
        while time.monotonic() < deadline:
            server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def wait_for_upload(directory: str | Path, timeout=45) -> dict:
    deadline = time.monotonic()+min(max(timeout, 0), 60)
    receipt = Path(directory)/"receipt.json"
    while True:
        if receipt.is_file():
            return {"state": "uploaded", "directory": str(Path(directory).resolve()),
                    "receipt": json.loads(receipt.read_text(encoding="utf-8"))}
        if time.monotonic() >= deadline:
            return {"state": "waiting", "next": "Continue waiting or ask the user to say continue after upload"}
        time.sleep(.25)
