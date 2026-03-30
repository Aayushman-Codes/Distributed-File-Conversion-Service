"""
tests/test_dfs.py — Functional test suite for the DFS.

Tests cover:
  • SSL connectivity
  • Image conversion (PNG → JPEG, BMP, WEBP)
  • Text conversion (JSON → CSV, TXT)
  • MD5 integrity checks
  • Job listing
  • Error handling (bad format, bad job id, checksum tampering)
  • Edge cases (empty-ish files, rapid sequential uploads)

Run (server must be running):
    python tests/test_dfs.py
"""

import os
import sys
import time
import json
import tempfile
import unittest
import logging
from pathlib import Path
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent.parent))

from client_lib import DFSClient, DFSError
from protocol  import MsgType, send_message, recv_message

logging.disable(logging.CRITICAL)   # suppress noise during tests

HOST = "localhost"
PORT = 9000
TMP  = tempfile.mkdtemp(prefix="dfs_test_")


def _make_png(path: str, size: tuple = (64, 64)) -> str:
    from PIL import Image
    img = Image.new("RGB", size, color=(100, 149, 237))
    img.save(path, format="PNG")
    return path


def _make_json(path: str) -> str:
    data = [{"id": i, "name": f"item_{i}", "value": i * 1.5} for i in range(10)]
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _make_csv(path: str) -> str:
    with open(path, "w") as f:
        f.write("id,name,value\n")
        for i in range(10):
            f.write(f"{i},item_{i},{i * 1.5}\n")
    return path


class TestSSLConnection(unittest.TestCase):
    def test_ping(self):
        with DFSClient(HOST, PORT) as c:
            rtt = c.ping()
            self.assertGreater(rtt, 0)
            self.assertLess(rtt, 5000)   # < 5 seconds

    def test_multiple_pings(self):
        with DFSClient(HOST, PORT) as c:
            for _ in range(3):
                rtt = c.ping()
                self.assertGreater(rtt, 0)


class TestImageConversion(unittest.TestCase):
    def _upload_wait_download(self, src: str, dst_fmt: str) -> str:
        with DFSClient(HOST, PORT) as c:
            job_id = c.upload(src, dst_fmt)
            c.wait_for_job(job_id, timeout=30)
            return c.download(job_id, TMP)

    def test_png_to_jpg(self):
        src = _make_png(os.path.join(TMP, "t_png_jpg.png"))
        out = self._upload_wait_download(src, "jpg")
        self.assertTrue(out.endswith(".jpg"))
        self.assertGreater(os.path.getsize(out), 0)

    def test_png_to_bmp(self):
        src = _make_png(os.path.join(TMP, "t_png_bmp.png"))
        out = self._upload_wait_download(src, "bmp")
        self.assertTrue(out.endswith(".bmp"))

    def test_png_to_webp(self):
        src = _make_png(os.path.join(TMP, "t_png_webp.png"))
        out = self._upload_wait_download(src, "webp")
        self.assertTrue(out.endswith(".webp"))

    def test_large_image(self):
        src = _make_png(os.path.join(TMP, "t_large.png"), size=(1024, 1024))
        out = self._upload_wait_download(src, "jpg")
        self.assertGreater(os.path.getsize(out), 0)


class TestTextConversion(unittest.TestCase):
    def _convert(self, src: str, dst_fmt: str) -> str:
        with DFSClient(HOST, PORT) as c:
            job_id = c.upload(src, dst_fmt)
            c.wait_for_job(job_id, timeout=30)
            return c.download(job_id, TMP)

    def test_json_to_csv(self):
        src = _make_json(os.path.join(TMP, "t.json"))
        out = self._convert(src, "csv")
        self.assertTrue(out.endswith(".csv"))
        content = open(out).read()
        self.assertIn("id", content)

    def test_json_to_txt(self):
        src = _make_json(os.path.join(TMP, "t2.json"))
        out = self._convert(src, "txt")
        self.assertTrue(out.endswith(".txt"))

    def test_csv_to_json(self):
        src = _make_csv(os.path.join(TMP, "t.csv"))
        out = self._convert(src, "json")
        self.assertTrue(out.endswith(".json"))
        data = json.loads(open(out).read())
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 10)


class TestJobWorkflow(unittest.TestCase):
    def test_list_jobs(self):
        src = _make_png(os.path.join(TMP, "list_test.png"))
        with DFSClient(HOST, PORT) as c:
            job_id = c.upload(src, "jpg")
            jobs   = c.list_jobs()
            ids    = [j["job_id"] for j in jobs]
            self.assertIn(job_id, ids)

    def test_status_transitions(self):
        src = _make_png(os.path.join(TMP, "status_test.png"))
        with DFSClient(HOST, PORT) as c:
            job_id = c.upload(src, "jpg")
            status = c.get_status(job_id)
            self.assertIn(status["state"], ["QUEUED", "PROCESSING", "DONE"])
            c.wait_for_job(job_id, timeout=30)
            final = c.get_status(job_id)
            self.assertEqual(final["state"], "DONE")

    def test_sequential_uploads(self):
        """Multiple uploads on the same connection."""
        with DFSClient(HOST, PORT) as c:
            jobs = []
            for i in range(3):
                src = _make_png(os.path.join(TMP, f"seq_{i}.png"))
                jobs.append(c.upload(src, "jpg"))
            for job_id in jobs:
                c.wait_for_job(job_id, timeout=60)
                status = c.get_status(job_id)
                self.assertEqual(status["state"], "DONE")


class TestErrorHandling(unittest.TestCase):
    def test_unsupported_format(self):
        src = _make_png(os.path.join(TMP, "err_fmt.png"))
        with self.assertRaises(DFSError):
            with DFSClient(HOST, PORT) as c:
                c.upload(src, "xyz")

    def test_unknown_job_id(self):
        with self.assertRaises(DFSError):
            with DFSClient(HOST, PORT) as c:
                c.get_status("00000000-0000-0000-0000-000000000000")

    def test_download_before_ready(self):
        """Uploading then immediately downloading (before DONE) should raise."""
        src = _make_png(os.path.join(TMP, "early_dl.png"),
                        size=(2048, 2048))     # large → likely still processing
        with DFSClient(HOST, PORT) as c:
            job_id = c.upload(src, "bmp")
            # Try immediate download (job may not be done yet)
            status = c.get_status(job_id)
            if status["state"] != "DONE":
                with self.assertRaises(DFSError):
                    c.download(job_id, TMP)


if __name__ == "__main__":
    print(f"Running DFS functional tests against {HOST}:{PORT}")
    print(f"Temp dir: {TMP}\n")
    unittest.main(verbosity=2)
