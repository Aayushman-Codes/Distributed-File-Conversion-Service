"""
converter.py — Actual file-conversion logic.

Supported conversions
  Images (via Pillow):  jpg/jpeg/png/bmp/gif/webp/tiff  ↔ any of the same
  Text   (built-in):    txt / csv / json                 ↔ any of the same

Returns the MD5 hex-digest of the output file.
"""

import os
import csv
import json
import hashlib
import logging
from io import StringIO

logger = logging.getLogger("converter")

# ── Format groups ─────────────────────────────────────────────────────────────
IMAGE_FORMATS = {"jpg", "jpeg", "png", "bmp", "gif", "webp", "tiff"}
TEXT_FORMATS  = {"txt", "csv", "json"}

# Pillow save-format names differ from extension names in a few cases
PIL_FORMAT_MAP = {
    "jpg":  "JPEG",
    "jpeg": "JPEG",
    "png":  "PNG",
    "bmp":  "BMP",
    "gif":  "GIF",
    "webp": "WEBP",
    "tiff": "TIFF",
}


def convert_file(in_path: str, out_path: str,
                 src_fmt: str, dst_fmt: str) -> str:
    """
    Convert *in_path* → *out_path*.
    Returns MD5 of the written output file.
    Raises ValueError for unsupported pairs, IOError on I/O problems.
    """
    src_fmt = src_fmt.lower()
    dst_fmt = dst_fmt.lower()

    if src_fmt in IMAGE_FORMATS and dst_fmt in IMAGE_FORMATS:
        _convert_image(in_path, out_path, dst_fmt)
    elif src_fmt in TEXT_FORMATS and dst_fmt in TEXT_FORMATS:
        _convert_text(in_path, out_path, src_fmt, dst_fmt)
    else:
        raise ValueError(
            f"Unsupported conversion: {src_fmt} → {dst_fmt}. "
            f"Images: {sorted(IMAGE_FORMATS)}, Text: {sorted(TEXT_FORMATS)}"
        )

    return _md5_file(out_path)


# ── Image conversion ──────────────────────────────────────────────────────────

def _convert_image(in_path: str, out_path: str, dst_fmt: str):
    from PIL import Image
    pil_fmt = PIL_FORMAT_MAP[dst_fmt]
    with Image.open(in_path) as img:
        # JPEG does not support alpha channel; convert to RGB if needed
        if pil_fmt == "JPEG" and img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.save(out_path, format=pil_fmt, quality=95)
    logger.debug("Image saved: %s (%s)", out_path, pil_fmt)


# ── Text conversion ───────────────────────────────────────────────────────────

def _convert_text(in_path: str, out_path: str, src_fmt: str, dst_fmt: str):
    with open(in_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Parse input
    if src_fmt == "json":
        data = json.loads(raw)
    elif src_fmt == "csv":
        reader = csv.DictReader(StringIO(raw))
        data = list(reader)
    else:  # txt → list of lines
        data = raw.splitlines()

    # Serialize output
    if dst_fmt == "json":
        out = json.dumps(data, indent=2, ensure_ascii=False)
    elif dst_fmt == "csv":
        if not data:
            out = ""
        elif isinstance(data, list) and isinstance(data[0], dict):
            buf = StringIO()
            writer = csv.DictWriter(buf, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            out = buf.getvalue()
        else:
            # Plain list → single-column CSV
            buf = StringIO()
            writer = csv.writer(buf)
            for item in data:
                writer.writerow([item])
            out = buf.getvalue()
    else:  # txt
        if isinstance(data, list):
            out = "\n".join(str(x) for x in data)
        else:
            out = str(data)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    logger.debug("Text saved: %s", out_path)


# ── Utility ───────────────────────────────────────────────────────────────────

def _md5_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
