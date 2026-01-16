"""
Async Job Manager for Long-Running Tasks.
异步任务管理器

Handles download and backtest jobs with progress tracking via WebSocket.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Callable, Coroutine
from dataclasses import dataclass, field

from ..models import JobStatus, JobType, JobInfo


@dataclass
class Job:
    """Job data structure / 任务数据结构"""
    job_id: str
    job_type: JobType
    status: JobStatus
    progress: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    result: Any = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    task: asyncio.Task | None = None

    def to_info(self) -> JobInfo:
        """Convert to JobInfo model"""
        return JobInfo(
            job_id=self.job_id,
            job_type=self.job_type,
            status=self.status,
            progress=self.progress,
            created_at=self.created_at.isoformat(),
            completed_at=self.completed_at.isoformat() if self.completed_at else None,
            error=self.error,
            metadata=self.metadata
        )


class JobManager:
    """
    Manages async jobs with progress tracking.
    管理异步任务并跟踪进度

    Features:
    - Submit and track long-running jobs
    - Progress updates via callback (for WebSocket)
    - Job result storage
    - Concurrent execution limit
    """

    def __init__(self, max_concurrent: int = 2):
        """
        Initialize job manager.

        Args:
            max_concurrent: Maximum concurrent jobs
        """
        self.max_concurrent = max_concurrent
        self.jobs: dict[str, Job] = {}
        self._running_count = 0
        self._lock = asyncio.Lock()
        self._ws_manager = None  # Set by app.py

    def set_ws_manager(self, ws_manager) -> None:
        """Set WebSocket manager for progress notifications"""
        self._ws_manager = ws_manager

    async def submit_job(
        self,
        job_type: JobType,
        task_func: Callable[..., Coroutine],
        progress_callback: Callable[[dict], Coroutine] | None = None,
        **kwargs
    ) -> str:
        """
        Submit a new job for async execution.

        Args:
            job_type: Type of job (download/backtest)
            task_func: Async function to execute
            progress_callback: Callback for progress updates
            **kwargs: Arguments to pass to task_func

        Returns:
            Job ID string
        """
        job_id = str(uuid.uuid4())[:8]

        job = Job(
            job_id=job_id,
            job_type=job_type,
            status=JobStatus.PENDING,
            metadata={"kwargs": {k: str(v)[:100] for k, v in kwargs.items()}}
        )

        self.jobs[job_id] = job

        # Create wrapper that handles progress and completion
        async def job_wrapper():
            async with self._lock:
                self._running_count += 1

            job.status = JobStatus.RUNNING
            await self._notify_progress(job_id, job_type, {
                "status": JobStatus.RUNNING.value,
                "progress_percent": 0.0
            })

            try:
                # Execute the task with progress callback
                result = await task_func(
                    progress_callback=lambda p: self._handle_progress(job_id, job_type, p),
                    **kwargs
                )

                job.result = result
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now()
                job.progress = 100.0

                await self._notify_completed(job_id, job_type, result)

            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now()
                await self._notify_failed(job_id, job_type, "Job cancelled")

            except Exception as e:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = datetime.now()
                await self._notify_failed(job_id, job_type, str(e))

            finally:
                async with self._lock:
                    self._running_count -= 1

        # Start the job task
        job.task = asyncio.create_task(job_wrapper())

        return job_id

    async def _handle_progress(
        self,
        job_id: str,
        job_type: JobType,
        progress: dict
    ) -> None:
        """Handle progress update from task"""
        if job_id in self.jobs:
            self.jobs[job_id].progress = progress.get("progress_percent", 0.0)
        await self._notify_progress(job_id, job_type, progress)

    async def _notify_progress(
        self,
        job_id: str,
        job_type: JobType,
        progress: dict
    ) -> None:
        """Send progress update via WebSocket"""
        if not self._ws_manager:
            return

        event_type = f"{job_type.value}_progress"
        message = {
            "type": event_type,
            "job_id": job_id,
            **progress
        }
        await self._ws_manager.broadcast(message)

    async def _notify_completed(
        self,
        job_id: str,
        job_type: JobType,
        result: Any
    ) -> None:
        """Send completion notification via WebSocket"""
        if not self._ws_manager:
            return

        # Send final progress
        await self._notify_progress(job_id, job_type, {
            "status": JobStatus.COMPLETED.value,
            "progress_percent": 100.0
        })

        # Send completion event
        message = {
            "type": "job_completed",
            "job_id": job_id,
            "job_type": job_type.value,
            "summary": self._extract_summary(result)
        }
        await self._ws_manager.broadcast(message)

    async def _notify_failed(
        self,
        job_id: str,
        job_type: JobType,
        error: str
    ) -> None:
        """Send failure notification via WebSocket"""
        if not self._ws_manager:
            return

        message = {
            "type": "job_failed",
            "job_id": job_id,
            "job_type": job_type.value,
            "error": error
        }
        await self._ws_manager.broadcast(message)

    def _extract_summary(self, result: Any) -> dict:
        """Extract summary from result for notification"""
        if isinstance(result, dict):
            # For backtest results, extract key metrics
            if "statistics" in result:
                stats = result["statistics"]
                return {
                    "total_return": stats.get("total_return"),
                    "sharpe_ratio": stats.get("sharpe_ratio"),
                    "max_drawdown": stats.get("max_ddpercent")
                }
            # For download results
            if "completed_symbols" in result:
                return {
                    "completed": len(result.get("completed_symbols", [])),
                    "failed": len(result.get("failed_symbols", []))
                }
        return {}

    def get_job(self, job_id: str) -> Job | None:
        """Get job by ID"""
        return self.jobs.get(job_id)

    def get_job_info(self, job_id: str) -> JobInfo | None:
        """Get job info by ID"""
        job = self.jobs.get(job_id)
        return job.to_info() if job else None

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending or running job.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if cancelled successfully
        """
        job = self.jobs.get(job_id)
        if not job:
            return False

        if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return False

        if job.task and not job.task.done():
            job.task.cancel()

        return True

    def list_jobs(
        self,
        job_type: JobType | None = None,
        status: JobStatus | None = None
    ) -> list[JobInfo]:
        """
        List jobs with optional filtering.

        Args:
            job_type: Filter by job type
            status: Filter by status

        Returns:
            List of JobInfo objects
        """
        jobs = list(self.jobs.values())

        if job_type:
            jobs = [j for j in jobs if j.job_type == job_type]

        if status:
            jobs = [j for j in jobs if j.status == status]

        # Sort by created_at descending
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        return [j.to_info() for j in jobs]

    def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """
        Remove old completed/failed jobs.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            Number of jobs removed
        """
        now = datetime.now()
        to_remove = []

        for job_id, job in self.jobs.items():
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                if job.completed_at:
                    age = (now - job.completed_at).total_seconds() / 3600
                    if age > max_age_hours:
                        to_remove.append(job_id)

        for job_id in to_remove:
            del self.jobs[job_id]

        return len(to_remove)
