"""Regression tests for JobQueue lifecycle (P0 fix, hardened).

Root cause being guarded: ``stop()`` used to kill the shared worker thread
unconditionally. A second FastAPI app/TestClient lifespan shutdown therefore
stopped the process-global queue while the primary app still needed it, so
later enqueued jobs never ran and the suite hung.

Ownership model: ``start()`` binds an opaque token to the CALLING thread
(each app lifespan runs on its own persistent event-loop thread). ``start()``
is idempotent per thread; ``stop()`` releases only the caller's own
ownership (or an explicit token) and is a no-op for non-owners. The worker
stops only when the last owner releases it, and restarts deterministically.
"""
import threading
import time

from fastapi.testclient import TestClient

from app.jobs.queue import JobQueue, get_job_queue
from app.main import create_app


def _wait_for(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class _App:
    """Simulates one independent app lifespan on its own dedicated thread."""

    def __init__(self, queue: JobQueue):
        self.queue = queue
        self.entered = threading.Event()
        self.release = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        self.queue.start()
        self.entered.set()
        self.release.wait(10)
        self.queue.stop()

    def shutdown(self):
        self.release.set()
        self.thread.join(timeout=5)


def test_same_owner_double_start_is_idempotent():
    q = JobQueue()
    token1 = q.start()
    token2 = q.start()  # same thread = same owner: must NOT count twice
    assert token1 is token2
    assert len(q._owners) == 1

    q.stop()
    assert q._running is False  # single owner fully released -> worker stops

    q.stop()  # repeated stop from same owner: no-op, cannot release others
    assert q._running is False


def test_double_stop_cannot_release_another_owner():
    q = JobQueue()
    app = _App(q)
    assert app.entered.wait(5)

    # The test thread owns nothing; its stop() calls must be harmless no-ops.
    q.stop()
    q.stop()
    assert q._running is True

    done = threading.Event()
    q.enqueue("still-alive", done.set)
    assert done.wait(5)

    app.shutdown()
    assert q._running is False


def test_two_independent_owners_release_independently():
    q = JobQueue()
    app1 = _App(q)
    app2 = _App(q)
    assert app1.entered.wait(5) and app2.entered.wait(5)
    assert len(q._owners) == 2

    app1.shutdown()  # first owner leaves
    assert q._running is True, "worker died while a second owner was still active"

    done = threading.Event()
    q.enqueue("between-owners", done.set)
    assert done.wait(5)

    app2.shutdown()  # last owner leaves
    assert q._running is False
    assert q._worker_thread is not None and not q._worker_thread.is_alive()


def test_queue_restarts_deterministically_after_full_stop():
    q = JobQueue()
    q.start()
    q.stop()
    assert q._running is False
    assert q._worker_thread is not None and not q._worker_thread.is_alive()

    q.start()
    assert q._running is True
    done = threading.Event()
    q.enqueue("after-restart", done.set)
    assert done.wait(5)
    q.stop()


def test_explicit_token_release_works_across_threads():
    q = JobQueue()
    box = {}

    def acquire():
        box["token"] = q.start()

    t = threading.Thread(target=acquire)
    t.start()
    t.join()
    assert q._running is True

    q.stop(box["token"])  # release from a DIFFERENT thread via explicit token
    assert q._running is False


def test_stop_without_matching_start_is_safe():
    q = JobQueue()
    q.stop()  # never started, owns nothing: must not raise or spawn a worker
    assert q._running is False


def test_idle_tracks_queued_and_running_jobs():
    q = JobQueue()
    q.start()
    try:
        assert q.idle()
        release = threading.Event()
        q.enqueue("blocking-job", lambda: release.wait(10))
        assert _wait_for(lambda: not q.idle()), "idle() never reported the running job"
        release.set()
        assert _wait_for(q.idle), "idle() never returned to True after job finished"
    finally:
        q.stop()


def test_concurrent_start_stop_is_thread_safe():
    q = JobQueue()
    threads = [
        threading.Thread(target=lambda: (q.start(), q.stop()), daemon=True)
        for _ in range(20)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not q._running
    assert not q._owners


def test_secondary_app_lifespan_cannot_kill_shared_worker(client):
    """End-to-end regression: exiting a second app's lifespan must not stop
    the process-global queue that the session app still owns."""
    queue = get_job_queue()
    with TestClient(create_app(), raise_server_exceptions=False):
        pass  # lifespan start+stop cycle on the SAME global queue

    # The session-scoped client still owns the queue: a job enqueued now must run.
    done = threading.Event()
    queue.enqueue("post-secondary-lifespan-probe", done.set)
    assert done.wait(10), "shared job queue worker was killed by a secondary lifespan"
