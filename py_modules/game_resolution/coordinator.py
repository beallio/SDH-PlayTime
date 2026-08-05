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
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if entry_timeout_seconds <= 0 or batch_timeout_seconds <= 0:
            raise ValueError("resolution time budgets must be positive")
        if adapters is None:
            adapters = (DirectExecutableAdapter(FilesystemProbe()),)
        self._adapter_registry = AdapterRegistry(adapters)
        self._entry_timeout_seconds = entry_timeout_seconds
        self._batch_timeout_seconds = batch_timeout_seconds
        self._monotonic = monotonic

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

    @staticmethod
    def _resolve_with_budget(
        adapter: ResolutionAdapter,
        request: ResolutionRequest,
        timeout_seconds: float,
    ) -> tuple[ResolutionResult | None, bool]:
        outcome: Queue[ResolutionResult | Exception] = Queue(maxsize=1)

        def resolve() -> None:
            try:
                outcome.put(adapter.resolve(request))
            except Exception as error:
                outcome.put(error)

        worker = threading.Thread(target=resolve, daemon=True)
        worker.start()
        try:
            item = outcome.get(timeout=timeout_seconds)
        except Empty:
            return None, True
        if isinstance(item, Exception) or not isinstance(item, ResolutionResult):
            return None, False
        return item, False
