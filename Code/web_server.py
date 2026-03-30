"""
web_server.py — HTTP bridge between the browser frontend and the DFS TCP server.

Architecture:
    Browser  ──HTTP──►  web_server.py  ──SSL/TCP──►  server.py
                        (port 8080)                   (port 9000)

Endpoints:
    GET  /                        → serve index.html
    GET  /api/ping                → ping the DFS server
    POST /api/convert             → upload file + target format, returns {job_id}
    GET  /api/status/<job_id>     → returns job status dict
    GET  /api/download/<job_id>   → streams converted file as download
    GET  /api/jobs                → list all jobs for this session
    GET  /api/formats             → return supported conversion map

Run:
    python web_server.py
    Then open http://localhost:8080 in your browser.
"""

import os
import sys
import json
import uuid
import socket
import logging
import tempfile
import mimetypes
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent))

from protocol import WEB_PORT, SUPPORTED_CONVERSIONS
from client_lib import DFSClient, DFSError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("web_server")

DFS_HOST = "localhost"
DFS_PORT = 9000
BASE_DIR = Path(__file__).parent

# Per-session job tracking (in-memory, keyed by session cookie)
_sessions: dict = {}
_sessions_lock = threading.Lock()


# ── HTTP Handler ──────────────────────────────────────────────────────────────

class DFSWebHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)

    def _session_id(self):
        cookies = self.headers.get("Cookie", "")
        for part in cookies.split(";"):
            part = part.strip()
            if part.startswith("dfs_session="):
                return part[len("dfs_session="):]
        return None

    def _send_json(self, data, status=200, session_id=None):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if session_id:
            self.send_header("Set-Cookie",
                             f"dfs_session={session_id}; Path=/; SameSite=Lax")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, msg, status=500):
        self._send_json({"error": msg}, status=status)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    # ── OPTIONS (CORS preflight) ──────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._serve_file(BASE_DIR / "frontend" / "index.html",
                             "text/html")
        elif path.startswith("/api/ping"):
            self._api_ping()
        elif path.startswith("/api/status/"):
            job_id = path.split("/api/status/")[-1]
            self._api_status(job_id)
        elif path.startswith("/api/download/"):
            job_id = path.split("/api/download/")[-1]
            self._api_download(job_id)
        elif path == "/api/jobs":
            self._api_jobs()
        elif path == "/api/formats":
            self._api_formats()
        else:
            # Try to serve static files from frontend/
            self._serve_static(parsed.path)

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")
        if path == "/api/convert":
            self._api_convert()
        else:
            self._send_error_json("Unknown endpoint", 404)

    # ── API handlers ──────────────────────────────────────────────────────────

    def _api_ping(self):
        try:
            with DFSClient(DFS_HOST, DFS_PORT) as c:
                rtt = c.ping()
            self._send_json({"status": "ok", "rtt_ms": round(rtt, 2)})
        except Exception as exc:
            self._send_error_json(f"DFS server unreachable: {exc}", 503)

    def _api_formats(self):
        self._send_json(SUPPORTED_CONVERSIONS)

    def _api_convert(self):
        """
        Expects multipart/form-data with:
          file   — the file bytes
          format — target format string (e.g. "jpg")
        Returns: {"job_id": "..."}
        """
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_error_json("Expected multipart/form-data", 400)
            return

        # Parse multipart boundary
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):].strip().encode()
                break
        if not boundary:
            self._send_error_json("Missing boundary", 400)
            return

        body = self._read_body()
        fields = _parse_multipart(body, boundary)

        file_data  = fields.get("file", {}).get("data")
        filename   = fields.get("file", {}).get("filename", "upload.bin")
        dst_format = fields.get("format", {}).get("data", b"").decode().strip()

        if not file_data or not dst_format:
            self._send_error_json("Missing file or format", 400)
            return

        # Get or create session
        session_id = self._session_id() or str(uuid.uuid4())
        with _sessions_lock:
            if session_id not in _sessions:
                _sessions[session_id] = []

        # Write to temp file and upload to DFS
        tmp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=Path(filename).suffix or ".bin"
        )
        try:
            tmp.write(file_data)
            tmp.close()
            with DFSClient(DFS_HOST, DFS_PORT) as c:
                job_id = c.upload(tmp.name, dst_format, original_name=filename)
            with _sessions_lock:
                _sessions[session_id].append({
                    "job_id":   job_id,
                    "filename": filename,
                    "dst_fmt":  dst_format,
                })
            self._send_json({"job_id": job_id}, session_id=session_id)
        except DFSError as exc:
            self._send_error_json(str(exc), 422)
        except Exception as exc:
            self._send_error_json(str(exc), 500)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    def _api_status(self, job_id):
        try:
            with DFSClient(DFS_HOST, DFS_PORT) as c:
                status = c.get_status(job_id)
            self._send_json(status)
        except DFSError as exc:
            self._send_error_json(str(exc), 404)
        except Exception as exc:
            self._send_error_json(str(exc), 500)

    def _api_download(self, job_id):
        tmp_dir = tempfile.mkdtemp()
        try:
            with DFSClient(DFS_HOST, DFS_PORT) as c:
                out_path = c.download(job_id, tmp_dir)
            with open(out_path, "rb") as f:
                data = f.read()
            # Use the filename the server computed (original stem + dst ext),
            # not the UUID-based storage name.
            filename = Path(out_path).name
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Disposition",
                             f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except DFSError as exc:
            self._send_error_json(str(exc), 404)
        except Exception as exc:
            self._send_error_json(str(exc), 500)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _api_jobs(self):
        session_id = self._session_id()
        if not session_id:
            self._send_json([])
            return
        with _sessions_lock:
            jobs = list(_sessions.get(session_id, []))
        # Enrich with current status and normalize field names
        enriched = []
        for j in jobs:
            try:
                with DFSClient(DFS_HOST, DFS_PORT) as c:
                    status = c.get_status(j["job_id"])
                j.update(status)
            except Exception:
                j["state"] = "UNKNOWN"
            # Normalize: always expose src_format and dst_format
            # (session stores dst_fmt; status dict stores dst_format + src_format)
            if "dst_format" not in j and "dst_fmt" in j:
                j["dst_format"] = j["dst_fmt"]
            if "dst_fmt" not in j and "dst_format" in j:
                j["dst_fmt"] = j["dst_format"]
            # filename vs original_name
            if "filename" not in j and "original_name" in j:
                j["filename"] = j["original_name"]
            enriched.append(j)
        self._send_json(enriched)

    # ── Static file serving ───────────────────────────────────────────────────

    def _serve_file(self, path: Path, content_type: str):
        if not path.exists():
            self._send_error_json(f"File not found: {path}", 404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, url_path: str):
        safe = url_path.lstrip("/")
        file_path = BASE_DIR / "frontend" / safe
        if not file_path.exists() or not file_path.is_file():
            self._send_error_json("Not found", 404)
            return
        mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self._serve_file(file_path, mime)


# ── Multipart parser ──────────────────────────────────────────────────────────

def _parse_multipart(body: bytes, boundary: bytes) -> dict:
    """Minimal multipart/form-data parser."""
    fields = {}
    delimiter = b"--" + boundary
    parts = body.split(delimiter)
    for part in parts[1:]:
        if part in (b"--\r\n", b"--", b""):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if b"\r\n\r\n" not in part:
            continue
        headers_raw, content = part.split(b"\r\n\r\n", 1)
        if content.endswith(b"\r\n"):
            content = content[:-2]
        headers_text = headers_raw.decode("utf-8", errors="replace")
        name     = None
        filename = None
        for hline in headers_text.splitlines():
            if "Content-Disposition" in hline:
                for token in hline.split(";"):
                    token = token.strip()
                    if token.startswith("name="):
                        name = token[5:].strip('"')
                    elif token.startswith("filename="):
                        filename = token[9:].strip('"')
        if name:
            fields[name] = {"data": content, "filename": filename}
    return fields


# ── Entry point ───────────────────────────────────────────────────────────────

def run_web_server(host: str = "0.0.0.0", port: int = WEB_PORT):
    os.makedirs(BASE_DIR / "frontend", exist_ok=True)
    server = HTTPServer((host, port), DFSWebHandler)

    # Resolve LAN IP for display
    try:
        lan_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        lan_ip = "<your-ip>"

    logger.info("=" * 60)
    logger.info("DFS Web Server running")
    logger.info("  Local:   http://localhost:%d", port)
    logger.info("  Network: http://%s:%d", lan_ip, port)
    logger.info("=" * 60)
    logger.info("If other devices get a connection error, open port %d", port)
    logger.info("  Windows (run PowerShell as Admin):")
    logger.info("    netsh advfirewall firewall add rule name=\"DFS Web\" "
                "protocol=TCP dir=in localport=%d action=allow", port)
    logger.info("  Linux:  sudo ufw allow %d/tcp", port)
    logger.info("=" * 60)
    logger.info("Make sure DFS server is also running:  python server.py")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Web server stopped.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="DFS Web Server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", default=WEB_PORT, type=int)
    ap.add_argument("--dfs-host", default=DFS_HOST)
    ap.add_argument("--dfs-port", default=DFS_PORT, type=int)
    args = ap.parse_args()
    DFS_HOST = args.dfs_host
    DFS_PORT = args.dfs_port
    run_web_server(args.host, args.port)
