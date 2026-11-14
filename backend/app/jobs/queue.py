"""Simple in-memory job queue for dataset processing.

This is intentionally lightweight and local-only. Queued work is lost when the
process restarts, so it is not production-durable and should not be treated as
a long-lived queue implementation for a real deployment.
"""
import threading
import time
from collections import deque
from typing import Callable, Optional

from app.core.logging import get_logger

log = get_logger("jobs")


class JobQueue:
    """Simple in-memory job queue with a single worker thread.

    This is suitable for SQLite local development. For PostgreSQL production,
    replace with a proper distributed job queue (Celery, RQ, etc.).
    """

    def __init__(self) -> None:
        self._queue: deque[tuple[str, Callable[[], None]]] = deque()
        self._results: dict[str, tuple[bool, Optional[str]]] = {}
        self._queued_ids: set[str] = set()
        self._active = 0
        # Owners are keyed by the thread that called start(). Each app lifespan
        # runs on its own persistent event-loop thread, so this identifies the
        # owning app without changing the start()/stop() call signature.
        self._owners: dict[int, object] = {}
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

    def start(self) -> object:
        """Acquire the queue for the calling owner and ensure the worker runs.

        Idempotent per calling thread: a second ``start()`` from the same
        lifespan returns the existing ownership token instead of counting a
        phantom second owner. Returns an opaque token that may be passed to
        ``stop(token)``; callers that ignore it can rely on thread binding.
        """
        ident = threading.get_ident()
        with self._lock:
            existing = self._owners.get(ident)
            if existing is not None:
                return existing
            token = object()
            self._owners[ident] = token
            if not self._running:
                self._running = True
                self._worker_thread = threading.Thread(target=self._worker, daemon=True)
                self._worker_thread.start()
        log.info("Job queue started")
        return token

    def stop(self, token: object | None = None) -> None:
        """Release ONE ownership. The worker stops only when no owners remain.

        With no argument, releases the ownership bound to the CALLING thread:
        a repeated ``stop()`` from the same owner is a no-op and can never
        release another app's ownership. An explicit *token* releases that
        specific owner regardless of calling thread. Queued-but-unprocessed
        jobs are dropped with the worker; this is the documented
        non-durable behavior and only happens at true shutdown.
        """
        thread = None
        with self._lock:
            if token is None:
                token = self._owners.pop(threading.get_ident(), None)
                if token is None:
                    return  # caller owns nothing: nothing to release
            else:
                for ident, owned in list(self._owners.items()):
                    if owned is token:
                        del self._owners[ident]
                        break
                else:
                    return  # unknown token: nothing to release
            if self._owners:
                log.debug(f"Job queue still has {len(self._owners)} active owner(s); worker keeps running")
                return
            self._running = False
            thread = self._worker_thread
        if thread is not None:
            thread.join(timeout=5)
        log.info("Job queue stopped")

    def enqueue(self, job_id: str, func: Callable[[], None]) -> None:
        """Enqueue a job to be processed."""
        with self._lock:
            if job_id in self._queued_ids:
                log.debug(f"Skipping duplicate enqueue for job {job_id}")
                return
            self._queue.append((job_id, func))
            self._queued_ids.add(job_id)
            self._results.setdefault(job_id, (False, None))
        log.debug(f"Enqueued job {job_id}")

    def get_result(self, job_id: str) -> Optional[tuple[bool, Optional[str]]]:
        """Get the result of a job: (completed, error_message)."""
        with self._lock:
            return self._results.get(job_id)

    def idle(self) -> bool:
        """True when no job is queued or currently executing."""
        with self._lock:
            return not self._queue and self._active == 0

    def _worker(self) -> None:
        """Worker thread that processes jobs sequentially."""
        while self._running:
            try:
                with self._lock:
                    if not self._queue:
                        time.sleep(0.1)
                        continue

                    job_id, func = self._queue.popleft()
                    self._queued_ids.discard(job_id)
                    self._active += 1

                log.info(f"Processing job {job_id}")
                try:
                    func()
                    with self._lock:
                        self._results[job_id] = (True, None)
                    log.info(f"Job {job_id} completed successfully")
                except Exception as e:
                    error_msg = str(e)
                    with self._lock:
                        self._results[job_id] = (True, error_msg)
                    log.error(f"Job {job_id} failed: {error_msg}", exc_info=True)
                finally:
                    with self._lock:
                        self._active -= 1
            except Exception as e:
                log.error(f"Worker error: {e}", exc_info=True)


# Global job queue instance
_job_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    """Get the global job queue instance."""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue()
    return _job_queue
