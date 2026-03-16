"""
tests/stress_test.py — Launches N concurrent clients that each upload
a file, wait for conversion, and download the result.

Usage:
    python tests/stress_test.py --clients 10 --size 100
"""

import os
import sys
import time
import random
import threading
import argparse
import logging
from pathlib import Path
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent.parent))

from client_lib import DFSClient, DFSError

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(threadName)-25s  %(message)s")

HOST = "localhost"
PORT = 9000


def make_png_bytes(size_kb: int) -> bytes:
    from PIL import Image
    side = max(8, int((size_kb * 1024 / 3) ** 0.5))
    img  = Image.new("RGB", (side, side),
                     color=(random.randint(0, 255),
                            random.randint(0, 255),
                            random.randint(0, 255)))
    buf  = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def client_worker(client_num: int, size_kb: int,
                  barrier: threading.Barrier,
                  results: list, tmp_dir: str):
    in_path = os.path.join(tmp_dir, f"stress_{client_num}.png")
    data    = make_png_bytes(size_kb)
    with open(in_path, "wb") as f:
        f.write(data)

    barrier.wait()    # all clients start simultaneously
    t0 = time.perf_counter()
    try:
        with DFSClient(HOST, PORT, poll_interval=0.2) as c:
            job_id = c.upload(in_path, "jpg")
            c.wait_for_job(job_id, timeout=120)
            c.download(job_id, tmp_dir)
        elapsed = time.perf_counter() - t0
        results[client_num] = {"ok": True, "elapsed": elapsed}
        logging.info("Client %d  DONE in %.2fs", client_num, elapsed)
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        results[client_num] = {"ok": False, "error": str(exc), "elapsed": elapsed}
        logging.error("Client %d  FAILED in %.2fs: %s", client_num, elapsed, exc)


def run_stress(n_clients: int, size_kb: int):
    import tempfile
    tmp = tempfile.mkdtemp(prefix="dfs_stress_")
    results = [None] * n_clients
    barrier = threading.Barrier(n_clients)
    threads = []

    print(f"\nStress test: {n_clients} concurrent clients, {size_kb} KB PNG→JPEG")
    print("─" * 60)

    for i in range(n_clients):
        t = threading.Thread(
            target=client_worker,
            args=(i, size_kb, barrier, results, tmp),
            name=f"stress-client-{i:02d}"
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Summary
    ok      = [r for r in results if r and r["ok"]]
    failed  = [r for r in results if r and not r["ok"]]
    elapsed = [r["elapsed"] for r in ok]

    print(f"\n{'─'*60}")
    print(f"Results: {len(ok)}/{n_clients} succeeded, {len(failed)} failed")
    if elapsed:
        import statistics
        print(f"  avg={statistics.mean(elapsed):.2f}s  "
              f"min={min(elapsed):.2f}s  max={max(elapsed):.2f}s")
    for r in failed:
        print(f"  FAIL: {r['error']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", default=8,  type=int)
    ap.add_argument("--size",    default=50, type=int, help="File size KB")
    ap.add_argument("--host",    default=HOST)
    ap.add_argument("--port",    default=PORT, type=int)
    args = ap.parse_args()
    HOST, PORT = args.host, args.port
    run_stress(args.clients, args.size)
