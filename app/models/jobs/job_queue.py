import heapq
import itertools
from typing import List

from .job import Job


class JobQueue:
    def __init__(self) -> None:
        self._heap: List[tuple[int, int, Job]] = []
        self._counter = itertools.count()

    def add_job(self, job: Job) -> None:
        if job is None:
            raise ValueError("job cannot be None")
        heapq.heappush(self._heap, (-int(job.job_priority), next(self._counter), job))

    def get_next_job(self) -> Job | None:
        if self._heap:
            return heapq.heappop(self._heap)[2]
        return None

    def peek_next_job(self) -> Job | None:
        if self._heap:
            return self._heap[0][2]
        return None

    def list_jobs(self) -> List[Job]:
        return [item[2] for item in sorted(self._heap)]

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def size(self) -> int:
        return len(self._heap)
