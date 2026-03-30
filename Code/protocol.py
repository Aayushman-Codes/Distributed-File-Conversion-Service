"""
protocol.py — Shared protocol constants, message framing, and data structures
for the Distributed File Conversion Service.
"""

import json
import struct
import socket
import hashlib

# ── Network ──────────────────────────────────────────────────────────────────
HOST            = "localhost"    # client default — same machine
SERVER_BIND     = "0.0.0.0"     # server listens on all interfaces
PORT            = 9000
WEB_PORT        = 8080           # HTTP frontend port
BUFFER_SIZE     = 65536
HEADER_LEN_FMT  = "!I"
HEADER_LEN_SIZE = struct.calcsize(HEADER_LEN_FMT)

# ── Supported conversion formats ─────────────────────────────────────────────
SUPPORTED_CONVERSIONS = {
    "jpg":  ["png", "bmp", "gif", "webp", "tiff"],
    "jpeg": ["png", "bmp", "gif", "webp", "tiff"],
    "png":  ["jpg", "bmp", "gif", "webp", "tiff"],
    "bmp":  ["png", "jpg", "gif", "webp"],
    "gif":  ["png", "jpg", "bmp"],
    "webp": ["png", "jpg", "bmp"],
    "tiff": ["png", "jpg", "bmp"],
    "txt":  ["csv", "json", "xml"],
    "csv":  ["txt", "json", "xml"],
    "json": ["txt", "csv", "xml"],
    "xml":  ["txt", "csv", "json"],
    "pdf":  ["txt", "docx"],
    "docx": ["txt", "pdf"],
}

class MsgType:
    UPLOAD_REQUEST   = "UPLOAD_REQUEST"
    UPLOAD_DATA      = "UPLOAD_DATA"
    JOB_ACCEPTED     = "JOB_ACCEPTED"
    JOB_STATUS       = "JOB_STATUS"
    DOWNLOAD_REQUEST = "DOWNLOAD_REQUEST"
    DOWNLOAD_DATA    = "DOWNLOAD_DATA"
    ERROR            = "ERROR"
    LIST_JOBS        = "LIST_JOBS"
    JOB_LIST         = "JOB_LIST"
    PING             = "PING"
    PONG             = "PONG"

class JobState:
    QUEUED     = "QUEUED"
    PROCESSING = "PROCESSING"
    DONE       = "DONE"
    FAILED     = "FAILED"

def send_message(sock, msg_type, header_extra=None, payload=b""):
    header = {"type": msg_type}
    if header_extra:
        header.update(header_extra)
    header_bytes = json.dumps(header).encode("utf-8")
    frame = (
        struct.pack(HEADER_LEN_FMT, len(header_bytes))
        + header_bytes
        + struct.pack(HEADER_LEN_FMT, len(payload))
        + payload
    )
    sock.sendall(frame)

def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(n - len(buf), BUFFER_SIZE))
        if not chunk:
            raise ConnectionError("Socket closed before all bytes received")
        buf.extend(chunk)
    return bytes(buf)

def recv_message(sock):
    raw_hlen = recv_exact(sock, HEADER_LEN_SIZE)
    hlen = struct.unpack(HEADER_LEN_FMT, raw_hlen)[0]
    header = json.loads(recv_exact(sock, hlen).decode("utf-8"))
    raw_plen = recv_exact(sock, HEADER_LEN_SIZE)
    plen = struct.unpack(HEADER_LEN_FMT, raw_plen)[0]
    payload = recv_exact(sock, plen) if plen else b""
    return header, payload

def md5_of_bytes(data):
    return hashlib.md5(data).hexdigest()
