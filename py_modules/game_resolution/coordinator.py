from __future__ import annotations

from collections.abc import Iterable
from queue import Empty, Queue
import threading
import time
from typing import Callable, Protocol

from .direct import DirectExecutableAdapter
from .filesystem import FilesystemProbe
from .models import (
    BatchResolutionResult,
    MAX_RESOLUTION_BATCH_SIZE,
    RequestValidationError,
    ResolutionRequest,
    ResolutionResult,
)


DEFAULT_ENTRY_TIMEOUT_SECONDS = 0.25
DEFAULT_BATCH_TIMEOUT_SECONDS = 2.0
DEFAULT_MAX_RESOLUTION_WORKERS = 4


class ResolutionAdapter(Protocol):
    launcher_kind: str

    def resolve(self, request: ResolutionRequest) -> ResolutionResult: ...


class AdapterRegistry:
    """The only shortcut kinds that may reach filesystem resolution."""

    def __init__(self, adapters: Iterable[ResolutionAdapter]) -> None:
        self._adapters = {adapter.launcher_kind: adapter for adapter in adapters}

    def get(self, launcher_kind: str) -> ResolutionAdapter | None:
        return self._adapters.get(launcher_kind)


class GameResolutionCoordinator:
    """Resolve only registered shortcut kinds from bounded, untrusted DTOs."""

    def __init__(
        self,
        adapters: Iterable[ResolutionAdapter] | None = None,
        *,
        entry_timeout_seconds: float = DEFAULT_ENTRY_TIMEOUT_SECONDS,
        batch_timeout_seconds: float = DEFAULT_BATCH_TIMEOUT_SECONDS,
        max_workers: int = DEFAULT_MAX_RESOLUTION_WORKERS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if entry_timeout_seconds <= 0 or batch_timeout_seconds <= 0 or max_workers <= 0:
            raise ValueError("resolution time budgets and worker cap must be positive")
        if adapters is None:
            adapters = (DirectExecutableAdapter(FilesystemProbe()),)
        self._adapter_registry = AdapterRegistry(adapters)
        self._entry_timeout_seconds = entry_timeout_seconds
        self._batch_timeout_seconds = batch_timeout_seconds
        self._monotonic = monotonic
        self._worker_slots = threading.BoundedSemaphore(max_workers)
        self._worker_lock = threading.Lock()
        self._workers: set[threading.Thread] = set()

    @property
    def live_worker_count(self) -> int:
        """Return the number of resolver calls currently occupying worker slots."""

        with self._worker_lock:
            return sum(worker.is_alive() for worker in self._workers)

    def wait_for_workers_to_finish(self, timeout_seconds: float) -> bool:
        """Wait for admitted work to return, primarily for controlled shutdown/tests."""

        deadline = time.monotonic() + timeout_seconds
        while self.live_worker_count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(remaining, 0.01))
        return True

    def resolve_batch(self, entries: object) -> BatchResolutionResult:
        if not isinstance(entries, list) or len(entries) > MAX_RESOLUTION_BATCH_SIZE:
            return BatchResolutionResult((), "malformed")

        deadline = self._monotonic() + self._batch_timeout_seconds
        results: list[ResolutionResult] = []
        for entry in entries:
            try:
                request = ResolutionRequest.from_mapping(entry)
            except RequestValidationError as error:
                results.append(ResolutionResult.unknown(reason_code=error.reason_code))
                continue
            except Exception:
                results.append(ResolutionResult.unknown(reason_code="probe_failure"))
                continue
            adapter = self._adapter_registry.get(request.launcher_kind)
            if adapter is None:
                results.append(
                    ResolutionResult.unknown(
                        request.launcher_kind,
                        request.classification_status,
                        "unsupported",
                    )
                )
                continue
            remaining_batch_time = deadline - self._monotonic()
            if remaining_batch_time <= 0:
                results.append(
                    ResolutionResult.unknown(
                        request.launcher_kind,
                        request.classification_status,
                        "timeout",
                    )
                )
                continue
            result, timed_out = self._resolve_with_budget(
                adapter,
                request,
                min(self._entry_timeout_seconds, remaining_batch_time),
            )
            if timed_out:
                results.append(
                    ResolutionResult.unknown(
                        request.launcher_kind,
                        request.classification_status,
                        "timeout",
                    )
                )
            elif result is None:
                results.append(
                    ResolutionResult.unknown(
                        request.launcher_kind,
                        request.classification_status,
                        "probe_failure",
                    )
                )
            else:
                results.append(result)
        return BatchResolutionResult(tuple(results))

    def _resolve_with_budget(
        self,
        adapter: ResolutionAdapter,
        request: ResolutionRequest,
        timeout_seconds: float,
    ) -> tuple[ResolutionResult | None, bool]:
        # Timed-out Python threads cannot safely be cancelled. Admit only a fixed
        # number of calls instead, and report saturation using the existing timeout
        # contract rather than queueing work behind a permanently stalled resolver.
        if not self._worker_slots.acquire(blocking=False):
            return None, True

        outcome: Queue[ResolutionResult | Exception] = Queue(maxsize=1)

        def resolve() -> None:
            try:
                outcome.put(adapter.resolve(request))
            except Exception as error:
                outcome.put(error)
            finally:
                with self._worker_lock:
                    self._workers.discard(threading.current_thread())
                self._worker_slots.release()

        worker = threading.Thread(
            target=resolve,
            daemon=True,
            name="game-resolution-worker",
        )
        with self._worker_lock:
            self._workers.add(worker)
        try:
            worker.start()
        except RuntimeError:
            with self._worker_lock:
                self._workers.discard(worker)
            self._worker_slots.release()
            return None, False
        try:
            item = outcome.get(timeout=timeout_seconds)
        except Empty:
            return None, True
        if isinstance(item, Exception) or not isinstance(item, ResolutionResult):
            return None, False
        return item, False
