"""
client_lib.py — Reusable DFS client library.

Usage:
    from client_lib import DFSClient

    with DFSClient() as c:
        job_id = c.upload("photo.png", "jpg")
        c.wait_for_job(job_id)
        c.download(job_id, output_dir="./results")
"""

import os
import ssl
import sys
import time
import socket
import hashlib
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from protocol import (
    HOST, PORT, BUFFER_SIZE,
    MsgType, JobState,
    send_message, recv_message, md5_of_bytes,
)

logger = logging.getLogger("dfs_client")

BASE_DIR  = Path(__file__).parent
CERT_FILE = BASE_DIR / "certs" / "server.crt"


class DFSError(Exception):
    """Raised when the server returns an ERROR message."""


class DFSClient:
    """
    Context-manager-friendly client for the Distributed File Conversion Service.

    Example
    -------
    with DFSClient(host="localhost", port=9000) as client:
        job_id = client.upload("image.png", "jpg")
        client.wait_for_job(job_id, timeout=60)
        client.download(job_id, output_dir=".")
    """

    def __init__(self, host: str = HOST, port: int = PORT,
                 poll_interval: float = 0.5):
        self.host          = host
        self.port          = port
        self.poll_interval = poll_interval
        self._sock: Optional[ssl.SSLSocket] = None

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self):
        """Establish SSL/TCP connection to the server."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(str(CERT_FILE))
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2

        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.connect((self.host, self.port))
        self._sock = ctx.wrap_socket(raw, server_hostname=self.host)
        logger.info("Connected to %s:%d  (cipher: %s)",
                    self.host, self.port, self._sock.cipher())

    def close(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    # ── Public API ────────────────────────────────────────────────────────────

    def ping(self) -> float:
        """Send a PING and return the round-trip time in milliseconds."""
        t0 = time.perf_counter()
        send_message(self._sock, MsgType.PING)
        hdr, _ = recv_message(self._sock)
        assert hdr["type"] == MsgType.PONG
        return (time.perf_counter() - t0) * 1000

    def upload(self, file_path: str, dst_format: str) -> str:
        """
        Upload *file_path* to the server requesting conversion to *dst_format*.
        Returns the job_id string.
        """
        path     = Path(file_path)
        src_fmt  = path.suffix.lstrip(".").lower()
        data     = path.read_bytes()
        checksum = md5_of_bytes(data)

        # Phase 1: request
        send_message(self._sock, MsgType.UPLOAD_REQUEST, {
            "src_format": src_fmt,
            "dst_format": dst_format.lower(),
            "filename":   path.name,
            "file_size":  len(data),
            "md5":        checksum,
        })
        hdr, _ = recv_message(self._sock)
        if hdr["type"] == MsgType.ERROR:
            raise DFSError(hdr.get("reason", "Unknown error"))
        assert hdr["type"] == MsgType.JOB_ACCEPTED, f"Unexpected: {hdr}"

        # Phase 2: data
        send_message(self._sock, MsgType.UPLOAD_DATA, {}, payload=data)
        hdr, _ = recv_message(self._sock)
        if hdr["type"] == MsgType.ERROR:
            raise DFSError(hdr.get("reason", "Upload error"))

        job_id = hdr.get("job_id")
        logger.info("Uploaded %s  →  job_id=%s", path.name, job_id)
        return job_id

    def get_status(self, job_id: str) -> dict:
        """Return the full job status dict."""
        send_message(self._sock, MsgType.JOB_STATUS, {"job_id": job_id})
        hdr, _ = recv_message(self._sock)
        if hdr["type"] == MsgType.ERROR:
            raise DFSError(hdr.get("reason"))
        return hdr

    def wait_for_job(self, job_id: str, timeout: float = 120) -> dict:
        """
        Poll until job reaches DONE or FAILED state, or *timeout* seconds elapse.
        Returns final status dict.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.get_status(job_id)
            state  = status.get("state")
            if state == JobState.DONE:
                logger.info("Job %s DONE", job_id)
                return status
            if state == JobState.FAILED:
                raise DFSError(f"Job {job_id} failed: {status.get('error_msg')}")
            logger.debug("Job %s state=%s, waiting %.1fs …",
                         job_id, state, self.poll_interval)
            time.sleep(self.poll_interval)
        raise TimeoutError(f"Job {job_id} did not complete in {timeout}s")

    def download(self, job_id: str, output_dir: str = ".") -> str:
        """
        Download converted file for *job_id* into *output_dir*.
        Returns the local file path.
        Verifies MD5 checksum automatically.
        """
        os.makedirs(output_dir, exist_ok=True)
        send_message(self._sock, MsgType.DOWNLOAD_REQUEST, {"job_id": job_id})
        hdr, payload = recv_message(self._sock)
        if hdr["type"] == MsgType.ERROR:
            raise DFSError(hdr.get("reason"))
        assert hdr["type"] == MsgType.DOWNLOAD_DATA, f"Unexpected: {hdr}"

        # Verify integrity
        server_md5 = hdr.get("md5", "")
        actual_md5 = md5_of_bytes(payload)
        if server_md5 and actual_md5 != server_md5:
            raise DFSError(
                f"Checksum mismatch (expected {server_md5}, got {actual_md5})"
            )

        out_path = os.path.join(output_dir, hdr["filename"])
        with open(out_path, "wb") as f:
            f.write(payload)
        logger.info("Downloaded %s  (%d bytes)", out_path, len(payload))
        return out_path

    def list_jobs(self) -> list[dict]:
        """Return a list of all jobs submitted by this client."""
        send_message(self._sock, MsgType.LIST_JOBS)
        hdr, _ = recv_message(self._sock)
        if hdr["type"] == MsgType.ERROR:
            raise DFSError(hdr.get("reason"))
        return hdr.get("jobs", [])
