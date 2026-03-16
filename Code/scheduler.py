"""
scheduler.py — Thread-safe job queue and scheduler for the DFS server.

Design:
 • Jobs are placed in a priority queue (smaller file → higher priority so
   short jobs do not wait behind multi-MB uploads).
 • A configurable pool of worker threads drains the queue.
 • Job state is kept in an in-memory dict (job_id → JobRecord).
"""

import os
import time
import uuid
import queue
import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from protocol import JobState

logger = logging.getLogger("scheduler")


@dataclass(order=True)
class JobRecord:
    """All metadata for one conversion job."""
    priority:        int            = field(compare=True)   # lower = higher priority
    job_id:          str            = field(compare=False)
    client_id:       str            = field(compare=False)
    src_format:      str            = field(compare=False)
    dst_format:      str            = field(compare=False)
    original_name:   str            = field(compare=False)
    file_size:       int            = field(compare=False)  # bytes
    input_path:      str            = field(compare=False)
    output_path:     str            = field(compare=False)
    state:           str            = field(compare=False, default=JobState.QUEUED)
    error_msg:       Optional[str]  = field(compare=False, default=None)
    queued_at:       float          = field(compare=False, default_factory=time.time)
    started_at:      Optional[float]= field(compare=False, default=None)
    finished_at:     Optional[float]= field(compare=False, default=None)
    checksum_in:     str            = field(compare=False, default="")
    checksum_out:    str            = field(compare=False, default="")

    def to_dict(self) -> dict:
        return {
            "job_id":        self.job_id,
            "client_id":     self.client_id,
            "original_name": self.original_name,
            "src_format":    self.src_format,
            "dst_format":    self.dst_format,
            "file_size":     self.file_size,
            "state":         self.state,
            "error_msg":     self.error_msg,
            "queued_at":     self.queued_at,
            "started_at":    self.started_at,
            "finished_at":   self.finished_at,
        }


class JobScheduler:
    """
    Manages job lifecycle:
      submit_job()  →  enqueues a JobRecord
      worker threads  →  pull from queue, call converter, update state
    """

    def __init__(self, num_workers: int = 4,
                 storage_dir: str = "/tmp/dfs_storage"):
        self._pq: queue.PriorityQueue = queue.PriorityQueue()
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._storage_dir = storage_dir
        os.makedirs(os.path.join(storage_dir, "input"),  exist_ok=True)
        os.makedirs(os.path.join(storage_dir, "output"), exist_ok=True)

        # Start worker threads
        self._workers: list[threading.Thread] = []
        for i in range(num_workers):
            t = threading.Thread(target=self._worker_loop,
                                 name=f"worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)
        logger.info("Scheduler started with %d workers", num_workers)

    # ── Public API ────────────────────────────────────────────────────────────

    def submit_job(self, client_id: str, src_format: str, dst_format: str,
                   original_name: str, file_data: bytes,
                   checksum_in: str = "") -> JobRecord:
        """Save uploaded data to disk, create a JobRecord, enqueue it."""
        job_id   = str(uuid.uuid4())
        priority = len(file_data)           # small files run first
        ext_in   = src_format.lower()
        ext_out  = dst_format.lower()
        in_path  = os.path.join(self._storage_dir, "input",  f"{job_id}.{ext_in}")
        out_path = os.path.join(self._storage_dir, "output", f"{job_id}.{ext_out}")

        with open(in_path, "wb") as f:
            f.write(file_data)

        job = JobRecord(
            priority      = priority,
            job_id        = job_id,
            client_id     = client_id,
            src_format    = ext_in,
            dst_format    = ext_out,
            original_name = original_name,
            file_size     = len(file_data),
            input_path    = in_path,
            output_path   = out_path,
            checksum_in   = checksum_in,
        )

        with self._lock:
            self._jobs[job_id] = job
        self._pq.put(job)
        logger.info("Job %s queued  (%s→%s, %d bytes)", job_id, ext_in, ext_out, len(file_data))
        return job

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, client_id: str) -> list[dict]:
        with self._lock:
            return [j.to_dict() for j in self._jobs.values()
                    if j.client_id == client_id]

    def all_stats(self) -> dict:
        with self._lock:
            counts = {s: 0 for s in [JobState.QUEUED, JobState.PROCESSING,
                                      JobState.DONE, JobState.FAILED]}
            for j in self._jobs.values():
                counts[j.state] += 1
        return {"queue_depth": self._pq.qsize(), "jobs": counts}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _worker_loop(self):
        from converter import convert_file          # local import to avoid circular
        while True:
            try:
                job: JobRecord = self._pq.get()
                self._update_state(job, JobState.PROCESSING)
                job.started_at = time.time()
                logger.info("Worker %s processing job %s",
                            threading.current_thread().name, job.job_id)
                try:
                    out_checksum = convert_file(
                        job.input_path, job.output_path,
                        job.src_format, job.dst_format
                    )
                    job.checksum_out = out_checksum
                    self._update_state(job, JobState.DONE)
                except Exception as exc:
                    logger.error("Job %s failed: %s", job.job_id, exc, exc_info=True)
                    job.error_msg = str(exc)
                    self._update_state(job, JobState.FAILED)
                finally:
                    job.finished_at = time.time()
                    self._pq.task_done()
            except Exception as exc:
                logger.critical("Worker crashed: %s", exc, exc_info=True)

    def _update_state(self, job: JobRecord, state: str):
        with self._lock:
            job.state = state
        logger.debug("Job %s → %s", job.job_id, state)
