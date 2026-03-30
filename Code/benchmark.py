"""
tests/benchmark.py — Performance evaluation for the DFS.

Measures:
  • Round-trip latency (ping)
  • Upload + conversion + download time per file size
  • Throughput (MB/s)
  • Concurrent-client scalability

Run:
    python tests/benchmark.py --concurrent 1 4 8 16
"""

import os
import sys
import time
import random
import threading
import statistics
import argparse
import logging
from pathlib import Path
from PIL import Image
import io

sys.path.insert(0, str(Path(__file__).parent.parent))

from client_lib import DFSClient, DFSError

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger("benchmark")

HOST = "localhost"
PORT = 9000

# ── Synthetic file generators ─────────────────────────────────────────────────

def make_png_bytes(size_kb: int) -> bytes:
    """Create a synthetic PNG image of approximately *size_kb* KB."""
    side = max(8, int((size_kb * 1024 / 3) ** 0.5))
    img  = Image.new("RGB", (side, side),
                     color=(random.randint(0, 255),
                            random.randint(0, 255),
                            random.randint(0, 255)))
    buf  = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_csv_bytes(size_kb: int) -> bytes:
    """Create a synthetic CSV of approximately *size_kb* KB."""
    lines  = ["id,name,value"]
    target = size_kb * 1024
    i = 0
    while len("\n".join(lines).encode()) < target:
        lines.append(f"{i},item_{i},{random.random():.6f}")
        i += 1
    return "\n".join(lines).encode("utf-8")


# ── Single job timing ─────────────────────────────────────────────────────────

def time_one_job(data: bytes, filename: str, dst_fmt: str,
                 tmp_dir: str = "/tmp/dfs_bench") -> dict:
    """Return timing dict for one complete upload→convert→download cycle."""
    os.makedirs(tmp_dir, exist_ok=True)
    in_path = os.path.join(tmp_dir, filename)
    with open(in_path, "wb") as f:
        f.write(data)

    times = {}
    try:
        with DFSClient(HOST, PORT, poll_interval=0.1) as c:
            t0 = time.perf_counter()
            job_id = c.upload(in_path, dst_fmt)
            times["upload_s"] = time.perf_counter() - t0

            t1 = time.perf_counter()
            c.wait_for_job(job_id, timeout=120)
            times["convert_s"] = time.perf_counter() - t1

            t2 = time.perf_counter()
            c.download(job_id, tmp_dir)
            times["download_s"] = time.perf_counter() - t2

            times["total_s"]      = time.perf_counter() - t0
            times["file_size_kb"] = len(data) / 1024
            times["throughput_kbps"] = (
                times["file_size_kb"] / times["total_s"]
            )
            times["error"] = None
    except Exception as exc:
        times["error"] = str(exc)
        times["total_s"] = time.perf_counter() - t0
    return times


# ── Benchmark suites ──────────────────────────────────────────────────────────

def bench_latency(n: int = 5):
    print(f"\n{'─'*60}")
    print(f"PING LATENCY  (n={n})")
    print(f"{'─'*60}")
    rtts = []
    with DFSClient(HOST, PORT) as c:
        for _ in range(n):
            rtts.append(c.ping())
    print(f"  min={min(rtts):.2f}ms  avg={statistics.mean(rtts):.2f}ms  "
          f"max={max(rtts):.2f}ms  stdev={statistics.stdev(rtts) if len(rtts)>1 else 0:.2f}ms")


def bench_file_sizes():
    sizes_kb = [1, 10, 50, 100, 500, 1000, 2000]
    print(f"\n{'─'*60}")
    print(f"FILE SIZE SCALABILITY  (PNG → JPEG)")
    print(f"{'─'*60}")
    print(f"{'Size (KB)':>10}  {'Upload(s)':>10}  {'Convert(s)':>11}  "
          f"{'Download(s)':>12}  {'Total(s)':>9}  {'Throughput(KB/s)':>16}")
    print(f"{'':>10}  {'─'*10}  {'─'*11}  {'─'*12}  {'─'*9}  {'─'*16}")

    for sz in sizes_kb:
        data = make_png_bytes(sz)
        r    = time_one_job(data, f"bench_{sz}kb.png", "jpg")
        if r["error"]:
            print(f"{sz:>10}  ERROR: {r['error']}")
        else:
            print(f"{sz:>10}  {r['upload_s']:>10.3f}  {r['convert_s']:>11.3f}  "
                  f"{r['download_s']:>12.3f}  {r['total_s']:>9.3f}  "
                  f"{r['throughput_kbps']:>16.1f}")


def bench_concurrent(num_clients_list: list[int]):
    sizes_kb = [50, 100]
    for sz in sizes_kb:
        data = make_png_bytes(sz)
        print(f"\n{'─'*60}")
        print(f"CONCURRENT CLIENTS  (file={sz} KB PNG→JPEG)")
        print(f"{'─'*60}")
        print(f"{'Clients':>8}  {'Avg Total(s)':>13}  {'Min(s)':>7}  "
              f"{'Max(s)':>7}  {'Errors':>7}  {'Throughput(KB/s)':>16}")
        print(f"{'':>8}  {'─'*13}  {'─'*7}  {'─'*7}  {'─'*7}  {'─'*16}")

        for n in num_clients_list:
            results  = [None] * n
            barrier  = threading.Barrier(n)
            threads  = []

            def worker(i=0):
                barrier.wait()           # all start simultaneously
                results[i] = time_one_job(data, f"concurrent_{i}_{sz}kb.png", "jpg")

            for i in range(n):
                t = threading.Thread(target=worker, args=(i,))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

            valid  = [r for r in results if r and not r["error"]]
            errors = n - len(valid)
            if valid:
                totals = [r["total_s"] for r in valid]
                tputs  = [r["throughput_kbps"] for r in valid]
                print(f"{n:>8}  {statistics.mean(totals):>13.3f}  "
                      f"{min(totals):>7.3f}  {max(totals):>7.3f}  "
                      f"{errors:>7}  {statistics.mean(tputs):>16.1f}")
            else:
                print(f"{n:>8}  ALL FAILED")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="DFS Benchmark")
    ap.add_argument("--host",       default=HOST)
    ap.add_argument("--port",       default=PORT, type=int)
    ap.add_argument("--concurrent", nargs="+", default=[1, 2, 4, 8], type=int,
                    help="List of concurrent client counts to test")
    ap.add_argument("--skip-sizes", action="store_true")
    ap.add_argument("--skip-concurrent", action="store_true")
    ap.add_argument("--ping-n",     default=5, type=int)
    args = ap.parse_args()

    global HOST, PORT
    HOST = args.host
    PORT = args.port

    print("=" * 60)
    print("  DFS PERFORMANCE BENCHMARK")
    print("=" * 60)

    bench_latency(args.ping_n)
    if not args.skip_sizes:
        bench_file_sizes()
    if not args.skip_concurrent:
        bench_concurrent(args.concurrent)

    print(f"\n{'─'*60}")
    print("Benchmark complete.")


if __name__ == "__main__":
    main()
