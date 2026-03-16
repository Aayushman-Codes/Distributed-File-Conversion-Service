#!/usr/bin/env python3
"""
client.py — Command-line interface for the DFS client.

Usage examples:
  python client.py upload photo.png --to jpg
  python client.py status <job_id>
  python client.py download <job_id> --out ./results
  python client.py convert photo.png --to jpg --out ./results   # one-shot
  python client.py jobs
  python client.py ping
"""

import sys
import time
import logging
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from protocol import HOST, PORT
from client_lib import DFSClient, DFSError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cli")


def cmd_ping(args):
    with DFSClient(args.host, args.port) as c:
        rtt = c.ping()
        print(f"PONG from {args.host}:{args.port}  RTT={rtt:.2f} ms")


def cmd_upload(args):
    with DFSClient(args.host, args.port) as c:
        job_id = c.upload(args.file, args.to)
        print(f"Job submitted: {job_id}")


def cmd_status(args):
    with DFSClient(args.host, args.port) as c:
        info = c.get_status(args.job_id)
        _print_job(info)


def cmd_download(args):
    with DFSClient(args.host, args.port) as c:
        path = c.download(args.job_id, args.out)
        print(f"Saved: {path}")


def cmd_jobs(args):
    with DFSClient(args.host, args.port) as c:
        jobs = c.list_jobs()
    if not jobs:
        print("No jobs found.")
        return
    print(f"{'JOB ID':<38}  {'FILE':<25}  {'SRC→DST':<12}  {'STATE'}")
    print("-" * 90)
    for j in jobs:
        conv = f"{j['src_format']}→{j['dst_format']}"
        print(f"{j['job_id']:<38}  {j['original_name']:<25}  {conv:<12}  {j['state']}")


def cmd_convert(args):
    """Upload, wait for completion, and download in one shot."""
    with DFSClient(args.host, args.port) as c:
        print(f"Uploading {args.file}  →  .{args.to} ...")
        t0 = time.perf_counter()
        job_id = c.upload(args.file, args.to)
        print(f"Job ID: {job_id}")

        print("Waiting for conversion ...")
        status = c.wait_for_job(job_id, timeout=args.timeout)
        elapsed = time.perf_counter() - t0

        out_path = c.download(job_id, args.out)
        size_mb  = status.get("file_size", 0) / (1024 * 1024)
        print(f"Done in {elapsed:.2f}s  —  saved to {out_path}  "
              f"({size_mb:.3f} MB input)")


def _print_job(j: dict):
    for k, v in j.items():
        if v is not None:
            print(f"  {k:<20} {v}")


# ── Argument parsing ──────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="DFS Client — Distributed File Conversion Service"
    )
    p.add_argument("--host", default=HOST)
    p.add_argument("--port", default=PORT, type=int)

    sub = p.add_subparsers(dest="command", required=True)

    # ping
    sub.add_parser("ping", help="Check server latency")

    # upload
    up = sub.add_parser("upload", help="Upload a file for conversion")
    up.add_argument("file",  help="Path to input file")
    up.add_argument("--to",  required=True, help="Target format (e.g. jpg)")

    # status
    st = sub.add_parser("status", help="Query job status")
    st.add_argument("job_id")

    # download
    dl = sub.add_parser("download", help="Download converted file")
    dl.add_argument("job_id")
    dl.add_argument("--out", default=".", help="Output directory")

    # jobs
    sub.add_parser("jobs", help="List all my jobs")

    # convert  (all-in-one)
    cv = sub.add_parser("convert", help="Upload, convert, and download in one step")
    cv.add_argument("file")
    cv.add_argument("--to",      required=True, help="Target format")
    cv.add_argument("--out",     default=".",   help="Output directory")
    cv.add_argument("--timeout", default=120,   type=float)

    return p


COMMANDS = {
    "ping":     cmd_ping,
    "upload":   cmd_upload,
    "status":   cmd_status,
    "download": cmd_download,
    "jobs":     cmd_jobs,
    "convert":  cmd_convert,
}

if __name__ == "__main__":
    parser = build_parser()
    args   = parser.parse_args()
    try:
        COMMANDS[args.command](args)
    except DFSError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
