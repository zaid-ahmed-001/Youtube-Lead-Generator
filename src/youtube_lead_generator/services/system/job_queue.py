import threading
import uuid
import time
from collections import deque

class ExtractionJobQueue:
    """
    Enterprise Persistent Extraction Job Queue.
    Manages pending, running, completed, and failed background jobs.
    """
    _lock = threading.Lock()
    _queue = deque()
    _jobs = {}

    @classmethod
    def add_job(cls, job_type: str, params: dict) -> str:
        job_id = str(uuid.uuid4())[:8]
        job = {
            "job_id": job_id,
            "job_type": job_type,
            "params": params,
            "status": "queued",
            "progress": 0,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "completed_at": None,
            "error": None
        }
        with cls._lock:
            cls._jobs[job_id] = job
            cls._queue.append(job_id)
        return job_id

    @classmethod
    def get_job(cls, job_id: str) -> dict:
        with cls._lock:
            return cls._jobs.get(job_id)

    @classmethod
    def list_jobs(cls) -> list:
        with cls._lock:
            return sorted(list(cls._jobs.values()), key=lambda j: j["created_at"], reverse=True)

    @classmethod
    def update_job(cls, job_id: str, status: str = None, progress: int = None, error: str = None):
        with cls._lock:
            job = cls._jobs.get(job_id)
            if job:
                if status: job["status"] = status
                if progress is not None: job["progress"] = progress
                if error: job["error"] = error
                if status in ("completed", "failed"):
                    job["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def clear_completed(cls):
        with cls._lock:
            cls._jobs = {k: v for k, v in cls._jobs.items() if v["status"] in ("queued", "running")}
