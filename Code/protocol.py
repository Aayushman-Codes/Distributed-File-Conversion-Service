"""
protocol.py — Shared protocol constants, message framing, and data structures
for the Distributed File Conversion Service.

Wire format for every message:
  [4 bytes: header length (big-endian uint32)]
  [N bytes: JSON header]
  [4 bytes: payload length (big-endian uint32)]
  [M bytes: raw binary payload  (may be 0 bytes)]
"""

import json
import struct
import socket
import hashlib

# ── Network ──────────────────────────────────────────────────────────────────
HOST            = "localhost"
PORT            = 9000
BUFFER_SIZE     = 65536          # 64 KB chunks for binary transfer
HEADER_LEN_FMT  = "!I"           # network-order unsigned 32-bit int
HEADER_LEN_SIZE = struct.calcsize(HEADER_LEN_FMT)

# ── Supported conversion formats ─────────────────────────────────────────────
SUPPORTED_CONVERSIONS = {
    # Images
    "jpg":  ["png", "bmp", "gif", "webp", "tiff"],
    "jpeg": ["png", "bmp", "gif", "webp", "tiff"],
    "png":  ["jpg", "bmp", "gif", "webp", "tiff"],
    "bmp":  ["png", "jpg", "gif", "webp"],
    "gif":  ["png", "jpg", "bmp"],
    "webp": ["png", "jpg", "bmp"],
    "tiff": ["png", "jpg", "bmp"],
    # Text
    "txt":  ["csv", "json"],
    "csv":  ["txt", "json"],
    "json": ["txt", "csv"],
}

# ── Message types ─────────────────────────────────────────────────────────────
class MsgType:
    UPLOAD_REQUEST   = "UPLOAD_REQUEST"    # client → server: want to convert
    UPLOAD_DATA      = "UPLOAD_DATA"       # client → server: binary file chunk
    JOB_ACCEPTED     = "JOB_ACCEPTED"      # server → client: job_id assigned
    JOB_STATUS       = "JOB_STATUS"        # bidirectional: poll / push status
    DOWNLOAD_REQUEST = "DOWNLOAD_REQUEST"  # client → server: fetch result
    DOWNLOAD_DATA    = "DOWNLOAD_DATA"     # server → client: binary file chunk
    ERROR            = "ERROR"             # either direction: error report
    LIST_JOBS        = "LIST_JOBS"         # client → server: list my jobs
    JOB_LIST         = "JOB_LIST"          # server → client: job list response
    PING             = "PING"
    PONG             = "PONG"

# ── Job states ────────────────────────────────────────────────────────────────
class JobState:
    QUEUED     = "QUEUED"
    PROCESSING = "PROCESSING"
    DONE       = "DONE"
    FAILED     = "FAILED"


# ── Low-level framing helpers ─────────────────────────────────────────────────

def send_message(sock: socket.socket, msg_type: str,
                 header_extra: dict = None, payload: bytes = b"") -> None:
    """Frame and send one message over *sock* (which may be an SSL socket)."""
    header = {"type": msg_type}
    if header_extra:
        header.update(header_extra)

    header_bytes = json.dumps(header).encode("utf-8")
    # Pack: [header-len][header-bytes][payload-len][payload-bytes]
    frame = (
        struct.pack(HEADER_LEN_FMT, len(header_bytes))
        + header_bytes
        + struct.pack(HEADER_LEN_FMT, len(payload))
        + payload
    )
    sock.sendall(frame)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly *n* bytes from *sock*, raising on EOF."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(n - len(buf), BUFFER_SIZE))
        if not chunk:
            raise ConnectionError("Socket closed before all bytes received")
        buf.extend(chunk)
    return bytes(buf)


def recv_message(sock: socket.socket) -> tuple[dict, bytes]:
    """Receive one framed message; returns (header_dict, payload_bytes)."""
    # Read header length
    raw_hlen = recv_exact(sock, HEADER_LEN_SIZE)
    hlen = struct.unpack(HEADER_LEN_FMT, raw_hlen)[0]

    # Read header JSON
    header = json.loads(recv_exact(sock, hlen).decode("utf-8"))

    # Read payload length + payload
    raw_plen = recv_exact(sock, HEADER_LEN_SIZE)
    plen = struct.unpack(HEADER_LEN_FMT, raw_plen)[0]
    payload = recv_exact(sock, plen) if plen else b""

    return header, payload


def md5_of_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()
