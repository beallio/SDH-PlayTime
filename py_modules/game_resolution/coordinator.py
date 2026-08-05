from __future__ import annotations

from collections.abc import Iterable

from .direct import DirectExecutableAdapter
from .filesystem import FilesystemProbe
from .models import (
    BatchResolutionResult,
    MAX_RESOLUTION_BATCH_SIZE,
    RequestValidationError,
    ResolutionRequest,
    ResolutionResult,
)


class AdapterRegistry:
    """The only shortcut kinds that may reach filesystem resolution."""

    def __init__(self, adapters: Iterable[DirectExecutableAdapter]) -> None:
        self._adapters = {adapter.launcher_kind: adapter for adapter in adapters}

    def get(self, launcher_kind: str) -> DirectExecutableAdapter | None:
        return self._adapters.get(launcher_kind)


class GameResolutionCoordinator:
    """Resolve only registered shortcut kinds from bounded, untrusted DTOs."""

    def __init__(
        self, adapters: Iterable[DirectExecutableAdapter] | None = None
    ) -> None:
        if adapters is None:
            adapters = (DirectExecutableAdapter(FilesystemProbe()),)
        self._adapter_registry = AdapterRegistry(adapters)

    def resolve_batch(self, entries: object) -> BatchResolutionResult:
        if not isinstance(entries, list) or len(entries) > MAX_RESOLUTION_BATCH_SIZE:
            return BatchResolutionResult((), "malformed")

        results: list[ResolutionResult] = []
        for entry in entries:
            try:
                request = ResolutionRequest.from_mapping(entry)
            except RequestValidationError as error:
                results.append(ResolutionResult.unknown(reason_code=error.reason_code))
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
            results.append(adapter.resolve(request))
        return BatchResolutionResult(tuple(results))
