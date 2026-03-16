"""
server.py — Distributed File Conversion Service — TCP + SSL Server

Architecture
  • One accept-loop thread listens on PORT.
  • Each accepted SSL connection gets its own daemon thread (ClientHandler).
  • All conversion work is delegated to JobScheduler which owns a worker-
    thread pool.  The server thread itself does no CPU-heavy work.

Message flow
  Upload:
    client  →  UPLOAD_REQUEST   (header: src_fmt, dst_fmt, filename, size, md5)
    server  →  JOB_ACCEPTED     (header: job_id)
    client  →  UPLOAD_DATA      (payload: raw file bytes)
    server  →  JOB_STATUS       (header: state=QUEUED)

  Poll:
    client  →  JOB_STATUS       (header: job_id)
    server  →  JOB_STATUS       (header: state, error_msg?)

  Download:
    client  →  DOWNLOAD_REQUEST (header: job_id)
    server  →  DOWNLOAD_DATA    (payload: converted file bytes)
               or ERROR

  List:
    client  →  LIST_JOBS
    server  →  JOB_LIST         (header: jobs=[...])
"""

import os
import ssl
import sys
import time
import socket
import logging
import hashlib
import threading
from pathlib import Path

# Allow importing sibling modules regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))

from protocol import (
    HOST, PORT, BUFFER_SIZE,
    MsgType, JobState,
    send_message, recv_message, md5_of_bytes,
    SUPPORTED_CONVERSIONS,
)
from scheduler import JobScheduler

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(threadName)-20s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("server")

BASE_DIR   = Path(__file__).parent
CERT_FILE  = BASE_DIR / "certs" / "server.crt"
KEY_FILE   = BASE_DIR / "certs" / "server.key"
STORAGE    = "/tmp/dfs_storage"


# ── SSL context ───────────────────────────────────────────────────────────────

def build_ssl_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(CERT_FILE), keyfile=str(KEY_FILE))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


# ── Per-client handler ────────────────────────────────────────────────────────

class ClientHandler:
    """Runs in its own thread; drives the protocol for one connected client."""

    def __init__(self, ssl_sock: ssl.SSLSocket, addr: tuple,
                 scheduler: JobScheduler):
        self.sock      = ssl_sock
        self.addr      = addr
        self.scheduler = scheduler
        # Use remote address as a simple client identifier
        self.client_id = f"{addr[0]}:{addr[1]}"

    def run(self):
        logger.info("Client connected: %s", self.client_id)
        try:
            while True:
                header, payload = recv_message(self.sock)
                self._dispatch(header, payload)
        except (ConnectionError, EOFError, ssl.SSLError) as exc:
            logger.info("Client %s disconnected: %s", self.client_id, exc)
        except Exception as exc:
            logger.error("Unexpected error with %s: %s", self.client_id, exc,
                         exc_info=True)
            try:
                send_message(self.sock, MsgType.ERROR,
                             {"reason": f"Server error: {exc}"})
            except Exception:
                pass
        finally:
            try:
                self.sock.close()
            except Exception:
                pass
            logger.info("Client %s handler exiting", self.client_id)

    def _dispatch(self, header: dict, payload: bytes):
        msg_type = header.get("type")
        logger.debug("← %s from %s", msg_type, self.client_id)

        if msg_type == MsgType.PING:
            send_message(self.sock, MsgType.PONG, {"server_time": time.time()})

        elif msg_type == MsgType.UPLOAD_REQUEST:
            self._handle_upload_request(header, payload)

        elif msg_type == MsgType.UPLOAD_DATA:
            self._handle_upload_data(header, payload)

        elif msg_type == MsgType.JOB_STATUS:
            self._handle_job_status(header)

        elif msg_type == MsgType.DOWNLOAD_REQUEST:
            self._handle_download(header)

        elif msg_type == MsgType.LIST_JOBS:
            self._handle_list_jobs()

        else:
            send_message(self.sock, MsgType.ERROR,
                         {"reason": f"Unknown message type: {msg_type}"})

    # ── Upload (two-phase) ────────────────────────────────────────────────────

    def _handle_upload_request(self, header: dict, _payload: bytes):
        src_fmt  = header.get("src_format", "").lower()
        dst_fmt  = header.get("dst_format", "").lower()
        filename = header.get("filename", "unknown")
        size     = int(header.get("file_size", 0))
        md5      = header.get("md5", "")

        # Validate
        allowed = SUPPORTED_CONVERSIONS.get(src_fmt, [])
        if dst_fmt not in allowed:
            send_message(self.sock, MsgType.ERROR, {
                "reason": f"Conversion {src_fmt}→{dst_fmt} not supported. "
                          f"Allowed targets for {src_fmt}: {allowed}"
            })
            return

        # Store pending upload info keyed by client (simple single-pending approach)
        self._pending = {
            "src_format": src_fmt, "dst_format": dst_fmt,
            "filename": filename,  "size": size, "md5": md5,
        }
        send_message(self.sock, MsgType.JOB_ACCEPTED, {
            "message": "Send UPLOAD_DATA with file bytes as payload"
        })
        logger.info("Upload request accepted from %s: %s→%s (%d bytes)",
                    self.client_id, src_fmt, dst_fmt, size)

    def _handle_upload_data(self, header: dict, payload: bytes):
        if not hasattr(self, "_pending") or not self._pending:
            send_message(self.sock, MsgType.ERROR,
                         {"reason": "No pending upload request"})
            return

        p = self._pending
        self._pending = {}

        # Integrity check
        actual_md5 = md5_of_bytes(payload)
        if p["md5"] and actual_md5 != p["md5"]:
            send_message(self.sock, MsgType.ERROR, {
                "reason": f"Checksum mismatch (expected {p['md5']}, got {actual_md5})"
            })
            return

        job = self.scheduler.submit_job(
            client_id    = self.client_id,
            src_format   = p["src_format"],
            dst_format   = p["dst_format"],
            original_name= p["filename"],
            file_data    = payload,
            checksum_in  = actual_md5,
        )
        send_message(self.sock, MsgType.JOB_STATUS, {
            "job_id": job.job_id,
            "state":  JobState.QUEUED,
        })
        logger.info("Job %s submitted by %s", job.job_id, self.client_id)

    # ── Status poll ───────────────────────────────────────────────────────────

    def _handle_job_status(self, header: dict):
        job_id = header.get("job_id")
        job = self.scheduler.get_job(job_id)
        if not job:
            send_message(self.sock, MsgType.ERROR,
                         {"reason": f"Job {job_id} not found"})
            return
        # Only the owning client may poll
        if job.client_id != self.client_id:
            send_message(self.sock, MsgType.ERROR,
                         {"reason": "Access denied"})
            return
        send_message(self.sock, MsgType.JOB_STATUS, job.to_dict())

    # ── Download ──────────────────────────────────────────────────────────────

    def _handle_download(self, header: dict):
        job_id = header.get("job_id")
        job = self.scheduler.get_job(job_id)

        if not job:
            send_message(self.sock, MsgType.ERROR,
                         {"reason": f"Job {job_id} not found"})
            return
        if job.client_id != self.client_id:
            send_message(self.sock, MsgType.ERROR,
                         {"reason": "Access denied"})
            return
        if job.state != JobState.DONE:
            send_message(self.sock, MsgType.ERROR, {
                "reason": f"Job not ready (state={job.state})"
            })
            return

        try:
            with open(job.output_path, "rb") as f:
                data = f.read()
        except OSError as exc:
            send_message(self.sock, MsgType.ERROR,
                         {"reason": f"Could not read output: {exc}"})
            return

        out_name = (Path(job.original_name).stem + "." + job.dst_format)
        send_message(self.sock, MsgType.DOWNLOAD_DATA, {
            "job_id":   job_id,
            "filename": out_name,
            "file_size": len(data),
            "md5":      md5_of_bytes(data),
        }, payload=data)
        logger.info("Job %s downloaded by %s (%d bytes)",
                    job_id, self.client_id, len(data))

    # ── List jobs ─────────────────────────────────────────────────────────────

    def _handle_list_jobs(self):
        jobs = self.scheduler.list_jobs(self.client_id)
        send_message(self.sock, MsgType.JOB_LIST, {"jobs": jobs})


# ── Server main loop ──────────────────────────────────────────────────────────

def run_server(host: str = HOST, port: int = PORT,
               num_workers: int = 4):
    scheduler  = JobScheduler(num_workers=num_workers, storage_dir=STORAGE)
    ssl_ctx    = build_ssl_context()
    raw_sock   = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    raw_sock.bind((host, port))
    raw_sock.listen(64)
    logger.info("DFS Server listening on %s:%d  (TLS, %d workers)",
                host, port, num_workers)

    try:
        while True:
            conn, addr = raw_sock.accept()
            try:
                ssl_conn = ssl_ctx.wrap_socket(conn, server_side=True)
            except ssl.SSLError as exc:
                logger.warning("TLS handshake failed from %s: %s", addr, exc)
                conn.close()
                continue

            handler = ClientHandler(ssl_conn, addr, scheduler)
            t = threading.Thread(target=handler.run,
                                 name=f"client-{addr[1]}", daemon=True)
            t.start()
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
    finally:
        raw_sock.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="DFS Server")
    ap.add_argument("--host",    default=HOST,  help="Bind address")
    ap.add_argument("--port",    default=PORT,  type=int)
    ap.add_argument("--workers", default=4,     type=int)
    args = ap.parse_args()
    run_server(args.host, args.port, args.workers)
